import base64
import hashlib
import hmac
import ipaddress
import math
import os
import re
import socket
import sys
import time
import uuid
import webbrowser
from io import BytesIO
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
from threading import Lock, Thread
from urllib.parse import urlsplit

import qrcode
from PIL import Image, UnidentifiedImageError
from dotenv import load_dotenv
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions
from werkzeug.middleware.proxy_fix import ProxyFix
from flask import (
    Flask,
    abort,
    current_app,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from google.api_core.exceptions import GoogleAPICallError

from customer_orders import (
    CustomerIdentityConfigurationError,
    OrderIdempotencyConflict,
    OrderPersistenceError,
    OrderRevisionConflict,
    OrderStatusTransitionError,
    aggregate_customer_orders,
    claim_customer_order_for_simulation,
    complete_customer_order_simulation,
    customer_identity_for_phone,
    fail_customer_order_simulation,
    get_authorized_customer_order,
    get_customer_order,
    list_customer_orders,
    list_simulation_orders,
    save_customer_order,
    update_customer_order,
    update_customer_order_status,
    update_customer_order_simulation_position,
)
from menu_catalog import (
    MenuCatalogError,
    MenuItemNotFoundError,
    create_menu_item,
    delete_menu_item,
    food_name_slug,
    list_menu_items,
    update_menu_item,
    validate_menu_item,
)
from firebase_db import (
    FirebaseConfigurationError,
    get_firebase_app,
)
from analytics import (
    AnalyticsConfigurationError,
    AnalyticsDataError,
    load_order_analytics,
)
from src.instruction_parser import parse_instruction
from src.task_decomposer import decompose_task
from src.action_generator import generate_action_sequence
from src.robot_controller import RobotController
from src.failure_detector import check_action, analyze_execution

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(
        encoding="utf-8",
        errors="backslashreplace"
    )

app = Flask(__name__)
load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
app.config["SECRET_KEY"] = os.environ.get("FLASK_SECRET_KEY") or None
try:
    trusted_proxy_hops = int(os.environ.get("TRUSTED_PROXY_HOPS", "0"))
except ValueError as error:
    raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.") from error
if trusted_proxy_hops < 0:
    raise RuntimeError("TRUSTED_PROXY_HOPS must be a non-negative integer.")
if trusted_proxy_hops:
    app.wsgi_app = ProxyFix(
        app.wsgi_app,
        x_for=trusted_proxy_hops,
        x_proto=trusted_proxy_hops,
        x_host=trusted_proxy_hops,
    )

ADMIN_SESSION_COOKIE = "admin_session"
ADMIN_SESSION_LIFETIME = timedelta(hours=12)
app.config["PERMANENT_SESSION_LIFETIME"] = ADMIN_SESSION_LIFETIME

ROBOT_TRACKING_LOCK = Lock()
ROBOT_TRACKING_STATE = {
    "demo_mode": True,
    "source": "Python RobotController demo",
    "controller_update_received": False,
    "status": "READY",
    "current_position": "COUNTER",
    "destination_table": None,
    "delivery_status": "Waiting for a ready demo order",
    "current_order_id": None,
    "current_order_customer": None,
    "current_order_items": [],
    "current_order_total": None,
    "battery": 100,
    "updated_at": None,
}
CUSTOMER_TABLES = tuple(range(1, 7))
MAX_CAMERA_FRAME_BYTES = 5 * 1024 * 1024
MAX_MENU_IMAGE_BYTES = 5 * 1024 * 1024
PERSON_DETECTION_THRESHOLD = 0.5
PERSON_DETECTION_MODEL = (
    Path(__file__).resolve().parent
    / "models"
    / "person_detection_mediapipe"
    / "person_detection_mediapipe_2023mar.onnx"
)


def _configured_admin_uids():
    configured = current_app.config.get(
        "FIREBASE_ADMIN_UIDS",
        os.environ.get("FIREBASE_ADMIN_UIDS", ""),
    )
    if isinstance(configured, (set, list, tuple)):
        return {str(uid).strip() for uid in configured if str(uid).strip()}
    return {
        uid.strip()
        for uid in str(configured).split(",")
        if uid.strip()
    }


def _firebase_auth_web_config():
    return {
        "apiKey": os.environ.get("FIREBASE_API_KEY", "").strip(),
        "signInUrl": (
            "https://identitytoolkit.googleapis.com/v1/"
            "accounts:signInWithPassword"
        ),
    }


def _safe_admin_next_path(target):
    if not isinstance(target, str) or not target.startswith("/"):
        return "/admin"
    if target.startswith("//") or "\\" in target or any(
        ord(character) < 32 or ord(character) == 127
        for character in target
    ):
        return "/admin"

    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc:
        return "/admin"
    if not (
        parsed.path == "/admin"
        or parsed.path.startswith("/admin/")
        or parsed.path in {"/robot-tracking", "/voice-camera"}
    ):
        return "/admin"
    return parsed.path + (
        f"?{parsed.query}" if parsed.query else ""
    ) + (
        f"#{parsed.fragment}" if parsed.fragment else ""
    )


def _local_admin_auth_configured():
    return (
        os.environ.get("FLASK_LOCAL_ADMIN", "").lower() in {"1", "true", "yes"}
        and bool(os.environ.get("LOCAL_ADMIN_PASSWORD"))
        and bool(app.secret_key)
    )


def _server_startup_config():
    configured_host = os.environ.get("FLASK_HOST", "127.0.0.1")
    configured_port = int(os.environ.get("PORT", "5000"))
    debug_enabled = (
        configured_host in {"127.0.0.1", "localhost"}
        and os.environ.get("FLASK_DEBUG", "1").lower() in {"1", "true", "yes"}
    )
    return configured_host, configured_port, debug_enabled


def _server_host_is_loopback(host):
    if host.lower() == "localhost":
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _validate_server_transport(host, ssl_context):
    if ssl_context is None and not _server_host_is_loopback(host):
        raise RuntimeError(
            "Refusing to serve Flask on a non-loopback address without HTTPS. "
            "Use scripts/start-mobile-https.ps1 for trusted local-network access."
        )
    if os.environ.get("PUBLIC_DEMO_MODE", "").lower() in {"1", "true", "yes"}:
        if ssl_context is not None or not _server_host_is_loopback(host):
            raise RuntimeError(
                "Public demo mode must use HTTP bound only to loopback; "
                "Cloudflare Quick Tunnel provides the public HTTPS endpoint."
            )
        public_url = _validated_public_demo_url(
            os.environ.get("PUBLIC_DEMO_URL", "")
        )
        qr_url = _validated_public_demo_url(
            os.environ.get("QR_BASE_URL", "")
        )
        if not public_url or qr_url != public_url:
            raise RuntimeError(
                "Set PUBLIC_DEMO_URL and QR_BASE_URL to the same HTTPS "
                "*.trycloudflare.com URL."
            )
        if trusted_proxy_hops != 1:
            raise RuntimeError(
                "Public demo mode requires TRUSTED_PROXY_HOPS=1 for "
                "Cloudflare's local tunnel proxy."
            )


def _server_ssl_context():
    certificate = os.environ.get("FLASK_TLS_CERT_FILE", "").strip()
    private_key = os.environ.get("FLASK_TLS_KEY_FILE", "").strip()
    if bool(certificate) != bool(private_key):
        raise RuntimeError(
            "Set both FLASK_TLS_CERT_FILE and FLASK_TLS_KEY_FILE for local HTTPS."
        )
    if not certificate:
        return None

    certificate_path = Path(certificate).expanduser()
    private_key_path = Path(private_key).expanduser()
    if not certificate_path.is_file() or not private_key_path.is_file():
        raise RuntimeError(
            "The configured Flask TLS certificate or private key file does not exist."
        )
    return (str(certificate_path), str(private_key_path))


def _admin_browser_path():
    return "/admin-login"


def _admin_browser_url(port, secure=False):
    scheme = "https" if secure else "http"
    return f"{scheme}://127.0.0.1:{port}{_admin_browser_path()}"


def _should_open_admin_browser(debug_enabled):
    return (
        not debug_enabled
        or os.environ.get("WERKZEUG_RUN_MAIN") == "true"
    )


def _is_same_origin_request():
    origin = request.headers.get("Origin", "")
    if not origin:
        return False
    try:
        parsed = urlsplit(origin)
        parsed.port
    except ValueError:
        return False
    return (
        parsed.scheme.lower() == request.scheme.lower()
        and parsed.netloc.lower() == request.host.lower()
        and not parsed.username
        and not parsed.password
    )


def _is_loopback_address(value):
    try:
        return ipaddress.ip_address(value).is_loopback
    except (TypeError, ValueError):
        return isinstance(value, str) and value.lower() == "localhost"


def _allows_insecure_admin_request():
    try:
        hostname = urlsplit(f"//{request.host}").hostname
    except ValueError:
        return False
    return (
        _is_loopback_address(hostname)
        and _is_loopback_address(request.remote_addr)
    )


def _public_demo_enabled():
    return os.environ.get("PUBLIC_DEMO_MODE", "").lower() in {
        "1",
        "true",
        "yes",
    }


def _validated_public_demo_url(value):
    normalized = _validated_customer_qr_url(value)
    if not normalized:
        return None
    try:
        parsed = urlsplit(normalized)
    except ValueError:
        return None
    hostname = (parsed.hostname or "").lower()
    if (
        parsed.scheme != "https"
        or not hostname.endswith(".trycloudflare.com")
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return normalized


def _public_demo_host():
    public_url = _validated_public_demo_url(
        os.environ.get("PUBLIC_DEMO_URL", "")
    )
    return urlsplit(public_url).netloc.lower() if public_url else None


PUBLIC_DEMO_CUSTOMER_ROUTES = {
    ("/customer/menu", "GET"),
    ("/customer/cart", "GET"),
    ("/customer/checkout", "GET"),
    ("/customer/my-orders", "GET"),
    ("/customer/order-status", "GET"),
    ("/api/customer/menu", "GET"),
    ("/api/customer/orders", "POST"),
    ("/static/css/customer.css", "GET"),
    ("/static/js/customer.js", "GET"),
}
PUBLIC_DEMO_ORDER_WINDOW_SECONDS = 600
PUBLIC_DEMO_ORDER_LIMIT = 10
PUBLIC_DEMO_ORDER_ATTEMPTS = {}
PUBLIC_DEMO_ORDER_LOCK = Lock()


def _is_public_demo_order_status_path(path):
    if not path.startswith("/api/customer/orders/"):
        return False
    order_id = path[len("/api/customer/orders/"):]
    return bool(re.fullmatch(r"[A-Za-z0-9_-]{1,100}", order_id))


def _is_public_demo_upload_path(path):
    if not path.startswith("/static/uploads/"):
        return False
    filename = path[len("/static/uploads/"):]
    return bool(filename) and all(
        part not in {"", ".", ".."}
        for part in filename.split("/")
    )


def _public_demo_route_allowed(path, method):
    if (path, method) in PUBLIC_DEMO_CUSTOMER_ROUTES:
        return True
    if method == "GET" and _is_public_demo_order_status_path(path):
        return True
    return method == "GET" and _is_public_demo_upload_path(path)


def _public_demo_client_ip():
    value = request.headers.get("CF-Connecting-IP", "").strip()
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return None


def _original_client_connection_ip():
    proxy_original = request.environ.get("werkzeug.proxy_fix.orig", {})
    return proxy_original.get("REMOTE_ADDR", request.remote_addr)


def _allow_public_demo_order(client_ip, now=None):
    if not client_ip:
        return False
    now = time.monotonic() if now is None else now
    cutoff = now - PUBLIC_DEMO_ORDER_WINDOW_SECONDS
    with PUBLIC_DEMO_ORDER_LOCK:
        for address in list(PUBLIC_DEMO_ORDER_ATTEMPTS):
            recent = [
                timestamp
                for timestamp in PUBLIC_DEMO_ORDER_ATTEMPTS[address]
                if timestamp > cutoff
            ]
            if recent:
                PUBLIC_DEMO_ORDER_ATTEMPTS[address] = recent
            else:
                del PUBLIC_DEMO_ORDER_ATTEMPTS[address]
        attempts = PUBLIC_DEMO_ORDER_ATTEMPTS.get(client_ip, [])
        if len(attempts) >= PUBLIC_DEMO_ORDER_LIMIT:
            return False
        if client_ip not in PUBLIC_DEMO_ORDER_ATTEMPTS:
            if len(PUBLIC_DEMO_ORDER_ATTEMPTS) >= 4096:
                return False
            PUBLIC_DEMO_ORDER_ATTEMPTS[client_ip] = attempts
        attempts.append(now)
        return True


def _admin_auth_error(message, status_code, api_request):
    if api_request:
        return jsonify({"success": False, "error": message}), status_code
    return abort(status_code, description=message)


@app.before_request
def restrict_public_demo_routes():
    if not _public_demo_enabled():
        return None
    public_host = _public_demo_host()
    forwarded_request = bool(
        request.headers.get("CF-Connecting-IP")
        or request.headers.get("X-Forwarded-Proto")
        or request.headers.get("X-Forwarded-Host")
        or request.host.lower() == (public_host or "")
    )
    if not forwarded_request:
        return None
    if (
        not _is_loopback_address(_original_client_connection_ip())
        or not request.is_secure
        or request.host.lower() != (public_host or "")
    ):
        abort(404)
    if not _public_demo_route_allowed(request.path, request.method):
        abort(404)
    if request.path == "/api/customer/orders" and request.method == "POST":
        content_length = request.content_length
        if content_length is None or content_length > 32 * 1024:
            return jsonify({
                "success": False,
                "error": "Order request is too large.",
            }), 413
        if not _allow_public_demo_order(_public_demo_client_ip()):
            return jsonify({
                "success": False,
                "error": "Too many demo order attempts. Please wait and try again.",
            }), 429
    return None


@app.before_request
def protect_admin_routes():
    path = request.path
    api_request = (
        path in {"/api/admin", "/api/robot-tracking", "/process"}
        or path.startswith("/api/admin/")
    )
    admin_page = (
        path == "/admin"
        or path.startswith("/admin/")
        or path in {"/robot-tracking", "/voice-camera", "/simulation"}
    )
    auth_page = path == "/admin-login"
    if (
        (api_request or admin_page or auth_page)
        and not request.is_secure
        and not _allows_insecure_admin_request()
    ):
        message = (
            "Admin access requires HTTPS unless opened on this computer via localhost."
        )
        if path.startswith("/api/admin/simulation/orders"):
            message = (
                "Simulation order data requires HTTPS from another device. "
                "Open this page through an HTTPS-enabled LAN address; "
                "admin sign-in is still required."
            )
        return _admin_auth_error(
            message,
            403,
            api_request,
        )
    if not api_request and not admin_page:
        return None
    if path in {"/api/admin/session", "/api/admin/local-session"}:
        return None
    if (
        _local_admin_auth_configured()
        and _allows_insecure_admin_request()
        and session.get("local_admin_authenticated") is True
    ):
        return None

    if not _configured_admin_uids():
        if api_request:
            return _admin_auth_error(
                "Admin access is not configured. Set FIREBASE_ADMIN_UIDS.",
                503,
                True,
            )
        return redirect(url_for("admin_login_page", setup_error="admin_uids"))

    session_cookie = request.cookies.get(ADMIN_SESSION_COOKIE)
    if not session_cookie:
        current_app.logger.warning(
            "Admin session cookie was missing on protected request to %s.",
            path,
        )
        if api_request:
            return _admin_auth_error("Admin sign-in is required.", 401, True)
        return redirect(url_for("admin_login_page", next=request.path))

    try:
        decoded = firebase_auth.verify_session_cookie(
            session_cookie,
            check_revoked=True,
            app=get_firebase_app(),
            clock_skew_seconds=30,
        )
    except (
        firebase_auth.InvalidSessionCookieError,
        firebase_auth.UserDisabledError,
        firebase_auth.UserNotFoundError,
        ValueError,
    ) as error:
        current_app.logger.warning(
            "Firebase rejected an admin session cookie on %s (%s).",
            path,
            type(error).__name__,
        )
        response = make_response(
            _admin_auth_error("Admin sign-in has expired.", 401, True)
            if api_request
            else redirect(url_for("admin_login_page", next=request.path))
        )
        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            "",
            expires=0,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            path="/",
        )
        return response
    except FirebaseConfigurationError:
        current_app.logger.error("Firebase Admin authentication is not configured.")
        return _admin_auth_error(
            "Admin authentication is temporarily unavailable.",
            503,
            api_request,
        )
    except firebase_exceptions.FirebaseError:
        current_app.logger.error("Could not verify the Firebase admin session.")
        return _admin_auth_error(
            "Admin authentication is temporarily unavailable.",
            503,
            api_request,
        )

    if decoded.get("uid") not in _configured_admin_uids():
        current_app.logger.warning(
            "A verified Firebase session was denied admin access on %s.",
            path,
        )
        response = make_response(
            _admin_auth_error("This account is not an administrator.", 403, True)
            if api_request
            else redirect(url_for("admin_login_page"))
        )
        response.set_cookie(
            ADMIN_SESSION_COOKIE,
            "",
            expires=0,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            path="/",
        )
        return response
    return None


@app.before_request
def require_secure_customer_order_api():
    path = request.path
    if not (
        path == "/api/customer/orders"
        or path.startswith("/api/customer/orders/")
    ):
        return None
    if request.is_secure or _allows_insecure_admin_request():
        return None
    return jsonify({
        "success": False,
        "error": "Customer order access requires HTTPS over the local network.",
    }), 403


@app.after_request
def prevent_simulation_order_cache(response):
    if request.path.startswith("/api/admin/simulation/orders"):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if (
        request.path == "/api/customer/orders"
        or request.path.startswith("/api/customer/orders/")
    ):
        response.headers["Cache-Control"] = "private, no-store, max-age=0"
    if request.path in {"/api/admin/menu", "/api/customer/menu"}:
        response.headers["Cache-Control"] = "no-store"
    return response


@lru_cache(maxsize=1)
def _get_person_detector():
    import cv2
    from models.person_detection_mediapipe.mp_persondet import MPPersonDet

    if not PERSON_DETECTION_MODEL.is_file():
        raise FileNotFoundError(
            f"Person detection model is missing: {PERSON_DETECTION_MODEL}"
        )

    detector = MPPersonDet(
        str(PERSON_DETECTION_MODEL),
        scoreThreshold=PERSON_DETECTION_THRESHOLD,
    )
    return cv2, detector


def _parse_customer_table(value, required=False):
    if value is None or value == "":
        if required:
            raise ValueError("A table number is required to place a dine-in order.")
        return None
    if isinstance(value, bool):
        raise ValueError("Table number must be an integer from 1 to 6.")
    if isinstance(value, int):
        table_number = value
    elif isinstance(value, str) and re.fullmatch(r"[1-6]", value.strip()):
        table_number = int(value)
    else:
        raise ValueError("Table number must be an integer from 1 to 6.")
    if table_number not in CUSTOMER_TABLES:
        raise ValueError("Table number must be from 1 to 6.")
    return table_number


def _validated_customer_order_items(submitted_items):
    if not isinstance(submitted_items, list) or not submitted_items or len(submitted_items) > 20:
        return None, None, "Add between 1 and 20 menu items."

    products = {
        item["id"]: item
        for item in list_menu_items()
    }
    order_items = []
    total_cents = 0
    for submitted_item in submitted_items:
        if not isinstance(submitted_item, dict):
            return None, None, "Each order item must include an item ID and quantity."
        product_id = submitted_item.get("id")
        product = products.get(product_id) if isinstance(product_id, str) else None
        quantity = submitted_item.get("quantity")
        if product is None:
            return None, None, "An order item is not on the sample menu."
        if not product["available"]:
            return None, None, f"{product['name']} is unavailable."
        if isinstance(quantity, bool) or not isinstance(quantity, int) or not 1 <= quantity <= 99:
            return None, None, "Item quantities must be between 1 and 99."
        price_cents = round(product["price"] * 100)
        total_cents += price_cents * quantity
        order_items.append({
            "id": product_id,
            "name": product["name"],
            "price": price_cents / 100,
            "quantity": quantity,
        })
    return order_items, total_cents, None


def _is_phone_reachable_hostname(hostname):
    if not hostname or any(character.isspace() for character in hostname):
        return False
    if hostname.lower().rstrip(".") in {
        "localhost",
        "localhost.localdomain",
    }:
        return False
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        labels = hostname.rstrip(".").split(".")
        return all(
            re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
            for label in labels
        )
    return not (address.is_loopback or address.is_unspecified)


def _validated_customer_qr_url(value, allow_loopback=False):
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        parsed.port
    except ValueError:
        return None
    if (
        parsed.scheme.lower() not in {"http", "https"}
        or not (
            allow_loopback and _is_loopback_address(hostname)
            or _is_phone_reachable_hostname(hostname)
        )
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        return None
    return f"{parsed.scheme.lower()}://{parsed.netloc}".rstrip("/")


def _customer_qr_base_url():
    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    if _public_demo_enabled():
        public_url = _validated_public_demo_url(
            os.environ.get("PUBLIC_DEMO_URL", "")
        )
        qr_url = _validated_public_demo_url(
            os.environ.get("QR_BASE_URL", "")
        )
        return public_url if public_url and qr_url == public_url else None
    if not request.is_secure:
        if _allows_insecure_admin_request():
            port = urlsplit(f"//{request.host}").port
            port_suffix = f":{port}" if port else ""
            return _validated_customer_qr_url(
                f"http://127.0.0.1{port_suffix}",
                allow_loopback=True,
            )
        return None

    configured_url = (
        os.environ.get("QR_BASE_URL", "").strip()
        or os.environ.get("CUSTOMER_QR_BASE_URL", "").strip()
    )
    if configured_url:
        if configured_url.lower().startswith("http://"):
            configured_url = "https://" + configured_url[len("http://"):]
        return _validated_customer_qr_url(configured_url)

    return _validated_customer_qr_url(
        f"{request.scheme}://{request.host}"
    )


def _customer_qr_image_data(url):
    qr_image = qrcode.make(url)
    buffer = BytesIO()
    qr_image.save(buffer, format="PNG")
    encoded = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _customer_table_qrs():
    base_url = _customer_qr_base_url()
    if not base_url:
        return base_url, []
    qr_codes = []
    for table_number in CUSTOMER_TABLES:
        url = f"{base_url}/customer/menu?table={table_number}"
        qr_codes.append({
            "table": table_number,
            "url": url,
            "image_data": _customer_qr_image_data(url),
        })
    return base_url, qr_codes


def instruction_error(message, error_code, status_code=400):

    if error_code == "INVALID_TABLE":

        robot_response = message

    elif error_code == "MISSING_DESTINATION":

        robot_response = (
            "Please specify a destination table number."
        )

    elif error_code == "MISSING_ITEMS":

        robot_response = (
            "Please specify the items for delivery."
        )

    else:

        robot_response = (
            "Sorry, I could not process your instruction. "
            "Please try again."
        )

    return jsonify({
        "success": False,
        "error": message,
        "error_code": error_code,
        "robot_response": robot_response
    }), status_code


def update_robot_tracking(robot, order, execution):
    overall_status = execution.get("overall_status", "UNKNOWN")
    robot_status = getattr(
        robot,
        "robot_status",
        execution.get("robot_status", "UNKNOWN"),
    )
    current_position = getattr(
        robot,
        "current_location",
        execution.get("current_location", "UNKNOWN"),
    )
    battery = getattr(robot, "battery", execution.get("battery"))
    with ROBOT_TRACKING_LOCK:
        ROBOT_TRACKING_STATE.update({
            "demo_mode": True,
            "source": "Python RobotController demo",
            "controller_update_received": True,
            "status": robot_status,
            "current_position": current_position,
            "destination_table": order.get("table"),
            "delivery_status": overall_status,
            "current_order_id": order.get("order_id", "DEMO-ORDER"),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })
        if battery is not None:
            ROBOT_TRACKING_STATE["battery"] = battery


def _number_words(number):
    words = {
        0: "zero",
        1: "one",
        2: "two",
        3: "three",
        4: "four",
        5: "five",
        6: "six",
        7: "seven",
        8: "eight",
        9: "nine",
        10: "ten",
    }
    return words.get(number, str(number))


def _item_phrase(item, quantity):
    name = item["name"]
    if name == "water" and quantity == 1:
        return "water"
    if quantity == 1:
        singular = {
            "plates of food": "plate of food",
            "water bottles": "water bottle",
            "cold drinks": "cold drink",
            "burgers": "burger",
            "pizzas": "pizza",
            "pastas": "pasta",
            "coffees": "coffee",
            "menus": "menu",
            "plates": "plate",
            "glasses": "glass",
            "drinks": "drink",
        }
        name = singular.get(name, name)
    else:
        plural = {
            "plate of food": "plates of food",
            "water bottle": "water bottles",
            "cold drink": "cold drinks",
            "burger": "burgers",
            "pizza": "pizzas",
            "pasta": "pastas",
            "coffee": "coffees",
            "menu": "menus",
            "plate": "plates",
            "glass": "glasses",
            "drink": "drinks",
        }
        name = plural.get(name, name)
    return f"{_number_words(quantity)} {name}"


def _join_phrases(phrases):
    if len(phrases) < 2:
        return phrases[0] if phrases else ""
    if len(phrases) == 2:
        return f"{phrases[0]} and {phrases[1]}"
    return f"{', '.join(phrases[:-1])}, and {phrases[-1]}"


def _order_plan_error(parsed_instruction, message, error_code):
    orders = parsed_instruction.get("orders", [])
    if error_code == "INVALID_TABLE":
        invalid_tables = {
            order["table"]
            for order in orders
            if isinstance(order.get("table"), int)
            and not 1 <= order["table"] <= 4
        }
        for order in orders:
            table = order.get("table")
            if table in invalid_tables:
                order["status"] = "INVALID_TABLE"
            elif table is None:
                order["status"] = "MISSING_DESTINATION"
            else:
                order["status"] = "VALIDATED"
            order["delivery_status"] = "NOT_STARTED"
            for item in order.get("items", []):
                item["delivery_status"] = "NOT_STARTED"
    elif error_code in {"MISSING_DESTINATION", "MISSING_ITEMS"}:
        for order in orders:
            order["status"] = error_code
            order["delivery_status"] = "NOT_STARTED"
            for item in order.get("items", []):
                item["delivery_status"] = "NOT_STARTED"

    return {
        "success": False,
        "error": message,
        "error_code": error_code,
        "robot_response": message,
        "parser": parsed_instruction,
        "order_plan": orders,
        "orders": orders,
        "overall_status": error_code,
    }, 400


def execute_delivery_orders(instruction, parsed_instruction):
    orders = parsed_instruction.get("orders", [])
    invalid_tables = sorted({
        order["table"]
        for order in orders
        if isinstance(order.get("table"), int)
        and not 1 <= order["table"] <= 4
    })
    if invalid_tables:
        available = "1, 2, 3, and 4"
        if len(invalid_tables) == 1:
            message = (
                f"Table {invalid_tables[0]} does not exist. "
                f"Available tables are {available}. "
                "Please select a valid table."
            )
        else:
            table_list = _join_phrases([
                str(number) for number in invalid_tables
            ])
            message = (
                f"Tables {table_list} do not exist. "
                f"Available tables are {available}. "
                "Please select a valid table."
            )
        if any(order.get("table") is None for order in orders):
            message += " Please also specify a destination for each remaining item."
        return _order_plan_error(
            parsed_instruction,
            message,
            "INVALID_TABLE",
        )

    if not orders or any(order.get("table") is None for order in orders):
        return _order_plan_error(
            parsed_instruction,
            "Please specify a destination table number.",
            "MISSING_DESTINATION",
        )

    if any(not order.get("items") for order in orders):
        return _order_plan_error(
            parsed_instruction,
            "Please specify the items for each destination table.",
            "MISSING_ITEMS",
        )

    task_plan = []
    action_plan = []
    commands = []
    execution_records = []
    robot = RobotController()

    for order in orders:
        order["status"] = "IN_PROGRESS"
        order["delivery_status"] = "IN_PROGRESS"
        for item in order["items"]:
            item["status"] = "IN_PROGRESS"
            item["delivery_status"] = "IN_PROGRESS"
            item_failed = False

            for unit_number in range(1, item["quantity"] + 1):
                single_item_instruction = {
                    "intent": "DELIVERY",
                    "actions": ["PICK", "PLACE"],
                    "object": item["name"],
                    "item": item["name"],
                    "quantity": 1,
                    "target": f"table {order['table']}",
                }
                task_steps = decompose_task(single_item_instruction)
                action_objects = generate_action_sequence(task_steps)
                if not action_objects:
                    raise RuntimeError(
                        f"No delivery actions generated for {item['name']}."
                    )

                robot_commands = [
                    action["action"]
                    for action in action_objects
                ]
                task_plan.append({
                    "order_id": order["order_id"],
                    "table": order["table"],
                    "item": item["name"],
                    "unit": unit_number,
                    "steps": task_steps,
                })
                action_plan.append({
                    "order_id": order["order_id"],
                    "table": order["table"],
                    "item": item["name"],
                    "unit": unit_number,
                    "actions": action_objects,
                })
                commands.extend(robot_commands)

                execution = robot.execute_sequence(
                    robot_commands,
                    object_name=item["name"],
                    target=f"table {order['table']}",
                )
                update_robot_tracking(robot, order, execution)
                unit_results = execution.get("results", [])
                unit_succeeded = (
                    execution.get("overall_status") == "SUCCESS"
                    and bool(unit_results)
                    and all(
                        result.get("status") == "SUCCESS"
                        for result in unit_results
                    )
                )
                if unit_succeeded:
                    item["delivered_quantity"] += 1
                else:
                    item_failed = True

                execution_records.append({
                    "order_id": order["order_id"],
                    "table": order["table"],
                    "item": item["name"],
                    "unit": unit_number,
                    **execution,
                })

            if not item_failed and item["delivered_quantity"] == item["quantity"]:
                item["status"] = "DELIVERED"
                item["delivery_status"] = "DELIVERED"
            elif item["delivered_quantity"]:
                item["status"] = "PARTIALLY_DELIVERED"
                item["delivery_status"] = "PARTIALLY_DELIVERED"
            else:
                item["status"] = "FAILED"
                item["delivery_status"] = "FAILED"

        if all(
            item["delivery_status"] == "DELIVERED"
            for item in order["items"]
        ):
            order["status"] = "DELIVERED"
            order["delivery_status"] = "DELIVERED"
        elif any(
            item["delivered_quantity"] > 0
            for item in order["items"]
        ):
            order["status"] = "PARTIALLY_DELIVERED"
            order["delivery_status"] = "PARTIALLY_DELIVERED"
        else:
            order["status"] = "FAILED"
            order["delivery_status"] = "FAILED"

    delivered_orders = [
        order for order in orders
        if order["delivery_status"] == "DELIVERED"
    ]
    orders_with_progress = [
        order for order in orders
        if order["delivery_status"] in {
            "DELIVERED",
            "PARTIALLY_DELIVERED",
        }
    ]
    all_delivered = len(delivered_orders) == len(orders)
    if all_delivered:
        overall_status = "SUCCESS"
    elif orders_with_progress:
        overall_status = "PARTIAL_FAILURE"
    else:
        overall_status = "FAILED"

    response_lines = []
    for order in orders:
        for item in order["items"]:
            ordered_phrase = _item_phrase(item, item["quantity"])
            table_name = f"Table {order['table']}"
            delivered_quantity = item["delivered_quantity"]
            if item["delivery_status"] == "DELIVERED":
                item_phrase = _item_phrase(item, item["quantity"])
                if not response_lines:
                    item_phrase = item_phrase.capitalize()
                response_lines.append(
                    f"{item_phrase} were delivered to {table_name}"
                    if item["quantity"] != 1
                    else f"{item_phrase} was delivered to {table_name}"
                )
            elif delivered_quantity:
                delivered_count = _number_words(delivered_quantity)
                quantity_phrase = _item_phrase(
                    item,
                    item["quantity"],
                )
                response_lines.append(
                    f"Delivery of {delivered_count} of "
                    f"{quantity_phrase} to {table_name} "
                    "was only partially completed"
                )
            else:
                response_lines.append(
                    f"Delivery of {ordered_phrase} to {table_name} failed"
                )

    if all_delivered:
        lead = (
            f"I have received {_number_words(len(orders))} "
            f"{'order' if len(orders) == 1 else 'orders'}."
        )
    else:
        lead = "Some deliveries could not be completed."

    robot_response = f"{lead} {_join_phrases(response_lines)}."
    flat_results = [
        result
        for record in execution_records
        for result in record.get("results", [])
    ]

    return {
        "success": all_delivered,
        "robot_response": robot_response,
        "instruction": instruction,
        "parser": parsed_instruction,
        "order_plan": orders,
        "orders": orders,
        "task_decomposition": task_plan,
        "action_sequence": action_plan,
        "robot_commands": commands,
        "robot_execution": execution_records,
        "checked_execution": flat_results,
        "failure_analysis": analyze_execution(flat_results),
        "overall_status": overall_status,
        "simulation": {
            "orders": orders,
            "actions": commands,
        },
    }, 200


# =========================================================
# HOME PAGE
# =========================================================

@app.route("/")
def home():
    return render_template("admin_dashboard/index.html")

# =========================================================
# 3D RESTAURANT SIMULATION
# =========================================================

@app.route("/simulation")
def simulation():
    return render_template("admin_dashboard/robot_3d.html")

# =========================================================
# VOICE + CAMERA PAGE
# =========================================================

@app.route("/voice-camera")
def voice_camera():
    return render_template("admin_dashboard/voice_camera.html")

# =========================================================
# ADMIN DEMO PAGES
# =========================================================

@app.route("/admin-login")
def admin_login_page():
    auth_config = _firebase_auth_web_config()
    return render_template(
        "admin_login.html",
        firebase_auth_config=auth_config,
        auth_config_ready=bool(
            auth_config["apiKey"] and _configured_admin_uids()
        ) or (
            _local_admin_auth_configured()
            and _allows_insecure_admin_request()
        ),
        local_admin_enabled=(
            _local_admin_auth_configured()
            and _allows_insecure_admin_request()
        ),
        admin_next_path=_safe_admin_next_path(request.args.get("next")),
        setup_error=request.args.get("setup_error", ""),
    )


@app.route("/api/admin/session", methods=["POST", "DELETE"])
def admin_session():
    if not _is_same_origin_request():
        return jsonify({
            "success": False,
            "error": "This request could not be verified.",
        }), 403

    if request.method == "DELETE":
        session.clear()
        response = jsonify({"success": True})
        response.delete_cookie(
            ADMIN_SESSION_COOKIE,
            httponly=True,
            secure=request.is_secure,
            samesite="Lax",
            path="/",
        )
        return response

    if not _configured_admin_uids():
        return jsonify({
            "success": False,
            "error": "Admin access is not configured. Set FIREBASE_ADMIN_UIDS.",
        }), 503

    data = request.get_json(silent=True)
    id_token = data.get("idToken") if isinstance(data, dict) else None
    if not isinstance(id_token, str) or not 100 <= len(id_token) <= 10_000:
        return jsonify({
            "success": False,
            "error": "A valid Firebase sign-in token is required.",
        }), 400

    auth_stage = "id_token_verification"
    try:
        firebase_app = get_firebase_app()
        decoded = firebase_auth.verify_id_token(
            id_token,
            check_revoked=True,
            clock_skew_seconds=30,
            app=firebase_app,
        )
        if decoded.get("uid") not in _configured_admin_uids():
            return jsonify({
                "success": False,
                "error": "This account is not an administrator.",
            }), 403
        auth_stage = "session_cookie_creation"
        session_cookie = firebase_auth.create_session_cookie(
            id_token,
            expires_in=ADMIN_SESSION_LIFETIME,
            app=firebase_app,
        )
    except FirebaseConfigurationError:
        current_app.logger.error("Firebase Admin authentication is not configured.")
        return jsonify({
            "success": False,
            "error": "Admin authentication is temporarily unavailable.",
        }), 503
    except firebase_auth.ExpiredIdTokenError:
        current_app.logger.warning(
            "Firebase rejected an expired admin ID token during %s.",
            auth_stage,
        )
        return jsonify({
            "success": False,
            "error": "Your Firebase sign-in token expired. Please sign in again.",
        }), 401
    except firebase_auth.RevokedIdTokenError:
        current_app.logger.warning(
            "Firebase rejected a revoked admin ID token during %s.",
            auth_stage,
        )
        return jsonify({
            "success": False,
            "error": "This Firebase sign-in session was revoked. Please sign in again.",
        }), 401
    except firebase_auth.InvalidIdTokenError:
        current_app.logger.warning(
            "Firebase rejected an admin ID token during %s.",
            auth_stage,
        )
        return jsonify({
            "success": False,
            "error": (
                "Firebase could not verify this sign-in token. Confirm the "
                "Firebase Web API key and service-account credentials belong "
                "to the same project, check your computer's clock, and sign "
                "in again."
            ),
        }), 401
    except firebase_auth.CertificateFetchError:
        current_app.logger.error(
            "Could not fetch Firebase public signing certificates during %s.",
            auth_stage,
        )
        return jsonify({
            "success": False,
            "error": (
                "Could not reach Firebase to verify this sign-in. Check the "
                "server internet connection and try again."
            ),
        }), 503
    except firebase_exceptions.FirebaseError:
        current_app.logger.exception(
            "Firebase admin authentication failed during %s.",
            auth_stage,
        )
        return jsonify({
            "success": False,
            "error": (
                "Firebase could not complete admin sign-in. Check the Flask "
                "terminal for the Firebase error and verify the project "
                "configuration."
            ),
        }), 503

    response = jsonify({"success": True})
    response.set_cookie(
        ADMIN_SESSION_COOKIE,
        session_cookie,
        max_age=int(ADMIN_SESSION_LIFETIME.total_seconds()),
        httponly=True,
        secure=request.is_secure,
        samesite="Lax",
        path="/",
    )
    return response


@app.route("/api/admin/local-session", methods=["POST"])
def local_admin_session():
    if not _is_same_origin_request() or not _allows_insecure_admin_request():
        return jsonify({
            "success": False,
            "error": "Local admin sign-in is available only on this computer.",
        }), 403
    if not _local_admin_auth_configured():
        return jsonify({
            "success": False,
            "error": "Local development sign-in is not configured.",
        }), 503

    data = request.get_json(silent=True)
    password = data.get("password") if isinstance(data, dict) else None
    configured_password = os.environ["LOCAL_ADMIN_PASSWORD"]
    if not isinstance(password, str) or not hmac.compare_digest(
        password, configured_password
    ):
        return jsonify({
            "success": False,
            "error": "Development password is incorrect.",
        }), 401

    session.clear()
    session.permanent = True
    session["local_admin_authenticated"] = True
    return jsonify({"success": True})


@app.route("/admin")
def admin_overview():
    return render_template(
        "admin_dashboard/admin_dashboard.html",
        active_page="dashboard",
        page_title="Restaurant Overview",
        page_heading="Restaurant overview",
        page_subtitle="A live-looking snapshot of your restaurant. All figures are demo data.",
    )


@app.route("/admin/orders")
def admin_orders():
    try:
        customer_orders = list_customer_orders()
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        abort(503, description=str(error))
    except (
        GoogleAPICallError,
        OrderPersistenceError,
        firebase_exceptions.FirebaseError,
    ):
        current_app.logger.error("Could not retrieve customer orders from Firestore.")
        abort(
            503,
            description="Order storage is temporarily unavailable. Please try again.",
        )
    return render_template(
        "admin_dashboard/admin_orders.html",
        active_page="orders",
        page_title="Orders Management",
        page_heading="Orders",
        page_subtitle="Customer QR orders saved in Firestore.",
        customer_orders=customer_orders,
    )


@app.route("/admin/robot")
def admin_robot():
    return render_template(
        "admin_dashboard/admin_robot.html",
        active_page="robot",
        page_title="Robot Management",
        page_heading="Robot management",
        page_subtitle="Monitor demo robot status. Controls below do not affect a real robot.",
    )


@app.route("/admin/menu")
def admin_menu():
    return render_template(
        "admin_dashboard/admin_menu.html",
        active_page="menu",
        page_title="Menu Management",
        page_heading="Menu management",
        page_subtitle="Manage the Firestore menu shown on customer QR pages.",
    )


@app.route("/api/admin/menu", methods=["GET", "POST"])
def admin_menu_api():
    if request.method == "GET":
        try:
            return jsonify({"success": True, "items": list_menu_items(seed_defaults=True)})
        except (
            FirebaseConfigurationError,
            GoogleAPICallError,
            MenuCatalogError,
            firebase_exceptions.FirebaseError,
        ):
            current_app.logger.exception("Could not load the Firestore menu.")
            return jsonify({
                "success": False,
                "error": "Menu data is temporarily unavailable.",
            }), 503

    if not _is_same_origin_request():
        return jsonify({
            "success": False,
            "error": "This request could not be verified.",
        }), 403
    try:
        item = validate_menu_item(request.get_json(silent=True))
        _validate_menu_image_exists(item)
    except MenuCatalogError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    try:
        created = create_menu_item(item)
        return jsonify({"success": True, "item": created}), 201
    except (
        FirebaseConfigurationError,
        GoogleAPICallError,
        MenuCatalogError,
        firebase_exceptions.FirebaseError,
    ):
        current_app.logger.exception("Could not create a Firestore menu item.")
        return jsonify({
            "success": False,
            "error": "Menu data is temporarily unavailable.",
        }), 503


@app.route("/api/admin/menu/<item_id>", methods=["PUT", "DELETE"])
def admin_menu_item_api(item_id):
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", item_id):
        return jsonify({"success": False, "error": "Invalid menu item ID."}), 400
    if not _is_same_origin_request():
        return jsonify({
            "success": False,
            "error": "This request could not be verified.",
        }), 403

    try:
        if request.method == "DELETE":
            delete_menu_item(item_id)
            return jsonify({"success": True})
        item = validate_menu_item(request.get_json(silent=True))
        _validate_menu_image_exists(item)
        updated = update_menu_item(item_id, item)
        return jsonify({"success": True, "item": updated})
    except MenuCatalogError as error:
        return jsonify({"success": False, "error": str(error)}), 400
    except MenuItemNotFoundError:
        return jsonify({
            "success": False,
            "error": "That menu item no longer exists.",
        }), 404
    except (
        FirebaseConfigurationError,
        GoogleAPICallError,
        firebase_exceptions.FirebaseError,
    ):
        current_app.logger.exception("Could not update the Firestore menu.")
        return jsonify({
            "success": False,
            "error": "Menu data is temporarily unavailable.",
        }), 503


@app.route("/api/admin/menu-images", methods=["POST"])
def upload_admin_menu_image():
    if not _is_same_origin_request():
        return jsonify({
            "success": False,
            "error": "This request could not be verified.",
        }), 403

    uploaded_file = request.files.get("image")
    if uploaded_file is None or not uploaded_file.filename:
        return jsonify({"success": False, "error": "Choose an image to upload."}), 400
    item_name = request.form.get("name", "").strip()
    if not 1 <= len(item_name) <= 80:
        return jsonify({
            "success": False,
            "error": "Enter an item name before uploading its image.",
        }), 400

    extension = Path(uploaded_file.filename).suffix.lower()
    allowed_formats = {
        ".jpg": "JPEG",
        ".jpeg": "JPEG",
        ".png": "PNG",
        ".webp": "WEBP",
    }
    if extension not in allowed_formats:
        return jsonify({
            "success": False,
            "error": "Use a JPG, JPEG, PNG, or WEBP image.",
        }), 400

    image_bytes = uploaded_file.stream.read(MAX_MENU_IMAGE_BYTES + 1)
    if not image_bytes:
        return jsonify({"success": False, "error": "The selected image is empty."}), 400
    if len(image_bytes) > MAX_MENU_IMAGE_BYTES:
        return jsonify({
            "success": False,
            "error": "Images must be 5 MB or smaller.",
        }), 413

    expected_format = allowed_formats[extension]
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            image_format = image.format
            width, height = image.size
            image.verify()
        if image_format != expected_format or width * height > 25_000_000:
            return jsonify({
                "success": False,
                "error": "The file content is not a supported image.",
            }), 400
        with Image.open(BytesIO(image_bytes)) as image:
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError):
        return jsonify({
            "success": False,
            "error": "The uploaded file is not a valid supported image.",
        }), 400

    upload_folder = Path(current_app.config.get(
        "MENU_UPLOAD_FOLDER",
        Path(current_app.root_path) / "static" / "uploads",
    ))
    name_slug = food_name_slug(item_name)
    filename = f"{name_slug}-{uuid.uuid4().hex[:8]}{extension}"
    destination = upload_folder / filename
    try:
        upload_folder.mkdir(parents=True, exist_ok=True)
        with destination.open("xb") as image_file:
            image_file.write(image_bytes)
    except OSError:
        current_app.logger.exception("Could not save an uploaded menu image.")
        return jsonify({
            "success": False,
            "error": "The image could not be saved. Check the uploads folder permissions.",
        }), 500

    return jsonify({
        "success": True,
        "image": f"uploads/{filename}",
        "url": url_for("static", filename=f"uploads/{filename}"),
    }), 201


def _validate_menu_image_exists(item):
    if not item["image"]:
        return
    upload_folder = Path(current_app.config.get(
        "MENU_UPLOAD_FOLDER",
        Path(current_app.root_path) / "static" / "uploads",
    ))
    image_path = upload_folder / Path(item["image"]).name
    if not image_path.is_file():
        raise MenuCatalogError("The selected food image was not found. Upload it again.")


@app.route("/admin/tables")
def admin_tables():
    qr_base_url, customer_qrs = _customer_table_qrs()
    return render_template(
        "admin_dashboard/admin_tables.html",
        active_page="tables",
        page_title="Tables & QR Codes",
        page_heading="Tables & QR codes",
        page_subtitle="Generate and print real customer menu QR codes for supported tables.",
        customer_qrs=customer_qrs,
        customer_qr_base_url=qr_base_url,
        customer_qr_local_demo=bool(
            customer_qrs
            and not request.is_secure
            and not _public_demo_enabled()
        ),
        customer_qr_public_demo=bool(
            customer_qrs and _public_demo_enabled()
        ),
        customer_tables=CUSTOMER_TABLES,
        customer_qr_by_table={
            qr["table"]: qr for qr in customer_qrs
        },
    )


@app.route("/admin/customers")
def admin_customers():
    return render_template(
        "admin_dashboard/admin_customers.html",
        active_page="customers",
        page_title="Customer Management",
        page_heading="Customers",
        page_subtitle="Customer activity derived from Firestore orders.",
    )


@app.route("/api/admin/customers", methods=["GET"])
def admin_customers_api():
    try:
        orders = list_customer_orders(limit=None, include_private=True)
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore customer data is not configured: %s", error)
        return jsonify({
            "success": False,
            "error": "Customer data is temporarily unavailable.",
        }), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not retrieve customer data from Firestore.")
        return jsonify({
            "success": False,
            "error": "Customer data is temporarily unavailable.",
        }), 503

    result = aggregate_customer_orders(orders)
    result.update({
        "success": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    })
    return jsonify(result)


@app.route("/admin/analytics")
def admin_analytics():
    return render_template(
        "admin_dashboard/admin_analytics.html",
        active_page="analytics",
        page_title="Analytics & Reports",
        page_heading="Analytics & reports",
        page_subtitle="Live order and robot delivery metrics from Firestore.",
    )


@app.route("/api/admin/analytics", methods=["GET"])
def admin_analytics_api():
    try:
        analytics = load_order_analytics(
            timezone_name=current_app.config.get(
                "RESTAURANT_TIMEZONE",
                os.environ.get("RESTAURANT_TIMEZONE", "UTC"),
            ),
            currency=current_app.config.get(
                "RESTAURANT_CURRENCY",
                os.environ.get("RESTAURANT_CURRENCY", ""),
            ),
        )
    except AnalyticsConfigurationError as error:
        current_app.logger.error("Analytics configuration is invalid: %s", error)
        return jsonify({
            "success": False,
            "error": "Analytics configuration is invalid.",
        }), 503
    except AnalyticsDataError as error:
        current_app.logger.error("Firestore analytics response was invalid: %s", error)
        return jsonify({
            "success": False,
            "error": "Analytics data is temporarily unavailable.",
        }), 503
    except FirebaseConfigurationError:
        current_app.logger.error("Firestore analytics is not configured.")
        return jsonify({
            "success": False,
            "error": "Analytics data is temporarily unavailable.",
        }), 503
    except (
        GoogleAPICallError,
        firebase_exceptions.FirebaseError,
    ) as error:
        current_app.logger.error(
            "Could not retrieve Firestore analytics (%s).",
            type(error).__name__,
        )
        return jsonify({
            "success": False,
            "error": "Analytics data is temporarily unavailable.",
        }), 503

    return jsonify({"success": True, **analytics})


@app.route("/admin/settings")
def admin_settings():
    return render_template(
        "admin_dashboard/admin_settings.html",
        active_page="settings",
        page_title="Restaurant Settings",
        page_heading="Settings",
        page_subtitle="Edit demo preferences. Changes are not saved to a server.",
    )


@app.route("/customer/menu")
def customer_menu():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_menu.html",
        table_number=table_number,
    )


@app.route("/api/customer/menu", methods=["GET"])
def customer_menu_api():
    try:
        items = list_menu_items()
    except (
        FirebaseConfigurationError,
        GoogleAPICallError,
        MenuCatalogError,
        firebase_exceptions.FirebaseError,
    ):
        current_app.logger.exception("Could not load the public customer menu.")
        return jsonify({
            "success": False,
            "error": "The menu is temporarily unavailable.",
        }), 503
    return jsonify({"success": True, "items": items})


@app.route("/customer/cart")
def customer_cart():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_cart.html",
        table_number=table_number,
    )


@app.route("/customer/checkout")
def customer_checkout():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_checkout.html",
        table_number=table_number,
    )


@app.route("/customer/order-status")
def customer_order_status():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_order_status.html",
        table_number=table_number,
    )


@app.route("/customer/robot-tracking")
def customer_robot_tracking():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_robot_tracking.html",
        table_number=table_number,
    )


@app.route("/customer/my-orders")
def customer_my_orders():
    try:
        table_number = _parse_customer_table(request.args.get("table"))
    except ValueError as error:
        abort(400, description=str(error))
    return render_template(
        "customer/customer_my_orders.html",
        table_number=table_number,
    )


@app.route("/api/customer/orders", methods=["POST"])
def create_customer_demo_order():
    if not _is_same_origin_request():
        return jsonify({
            "success": False,
            "error": "This request could not be verified.",
        }), 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "A JSON order is required."}), 400

    try:
        table_number = _parse_customer_table(data.get("table_number"), required=True)
    except ValueError as error:
        return jsonify({"success": False, "error": str(error)}), 400

    customer_name = re.sub(r"\s+", " ", str(data.get("customer_name", "")).strip())
    if len(customer_name) < 2 or len(customer_name) > 80:
        return jsonify({"success": False, "error": "Enter a full name between 2 and 80 characters."}), 400

    phone = str(data.get("customer_phone", "")).strip()
    phone_digits = re.sub(r"\D", "", phone)
    if not 10 <= len(phone_digits) <= 15:
        return jsonify({"success": False, "error": "Enter a valid mobile number with 10–15 digits."}), 400

    try:
        order_items, total_cents, item_error = _validated_customer_order_items(
            data.get("items")
        )
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore menu configuration is not available: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, firebase_exceptions.FirebaseError):
        current_app.logger.exception("Could not read the Firestore menu before checkout.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    except MenuCatalogError:
        current_app.logger.exception("Could not validate the current menu for checkout.")
        return jsonify({
            "success": False,
            "error": "Menu data is temporarily unavailable. Please try again.",
        }), 503
    if item_error:
        return jsonify({"success": False, "error": item_error}), 400

    idempotency_key = request.headers.get("Idempotency-Key", "").strip()
    if len(idempotency_key) > 256:
        return jsonify({
            "success": False,
            "error": "The checkout request key must be 256 characters or fewer.",
        }), 400

    access_token = request.headers.get("X-Order-Access-Token", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{40,100}", access_token):
        return jsonify({
            "success": False,
            "error": "A valid order access token is required.",
        }), 400

    try:
        customer_identity = customer_identity_for_phone(phone_digits)
    except CustomerIdentityConfigurationError as error:
        current_app.logger.error(
            "Customer identity configuration is invalid: %s",
            error,
        )
        return jsonify({
            "success": False,
            "error": "Customer identity is temporarily unavailable. Please contact the restaurant.",
        }), 503

    order = {
        "customer_name": customer_name,
        "phone_last4": phone_digits[-4:],
        "customer_identity": customer_identity,
        "table_number": table_number,
        "items": order_items,
        "total": total_cents / 100,
        "status": "Order Placed",
        "status_updated_at": datetime.now(timezone.utc),
        "revision": 0,
        "order_access_token_hash": hashlib.sha256(
            access_token.encode("utf-8")
        ).hexdigest(),
        "demo_only": True,
    }
    try:
        order = save_customer_order(order, idempotency_key or None)
    except OrderIdempotencyConflict as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({
            "success": False,
            "error": str(error),
        }), 503
    except (
        GoogleAPICallError,
        OrderPersistenceError,
        firebase_exceptions.FirebaseError,
    ):
        current_app.logger.error("Could not save customer order to Firestore.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503

    return jsonify({
        "success": True,
        "order": order,
        "access_token": access_token,
    }), 201


@app.route("/api/customer/orders/<order_id>", methods=["GET"])
def get_customer_order_status(order_id):
    access_token = request.headers.get("X-Order-Access-Token", "")
    try:
        order = get_authorized_customer_order(order_id, access_token)
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not retrieve customer order from Firestore.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503

    if order is None:
        return jsonify({"success": False, "error": "Order not found."}), 404
    return jsonify({"success": True, "order": order})


@app.route(
    "/api/customer/orders/<order_id>/tracking",
    methods=["GET"],
)
def get_customer_order_tracking(order_id):
    if not request.is_secure and not _allows_insecure_admin_request():
        return jsonify({
            "success": False,
            "error": "Customer robot tracking requires HTTPS over the local network.",
        }), 403

    access_token = request.headers.get("X-Order-Access-Token", "")
    try:
        order = get_authorized_customer_order(order_id, access_token)
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({
            "success": False,
            "error": "Order tracking is temporarily unavailable.",
        }), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not retrieve customer tracking data.")
        return jsonify({
            "success": False,
            "error": "Order tracking is temporarily unavailable.",
        }), 503

    if order is None:
        return jsonify({"success": False, "error": "Order not found."}), 404

    status = order.get("status", "Unknown")
    simulated = order.get("demo_only") is True
    position = order.get("delivery_simulation_position")
    if not simulated or not isinstance(position, dict):
        position = None
    else:
        position_time = position.get("updated_at")
        position = {
            "x": position.get("x"),
            "z": position.get("z"),
            "moving": position.get("moving") is True,
            "updated_at": (
                position_time.isoformat(timespec="seconds")
                if isinstance(position_time, datetime)
                else position_time
            ),
        }

    if not simulated:
        message = "Live robot tracking is not available for this order."
    elif status == "Robot Delivery" and order.get("delivery_simulation_state") == "in_progress":
        message = (
            "Your simulated robot is on its way."
            if position and position["moving"]
            else "Your simulated robot is waiting to continue."
        )
    elif status == "Delivered":
        message = "Your order has been delivered."
    elif status in {"Cancelled", "Failed"}:
        message = f"Your order is {status.lower()}."
    elif status == "Ready":
        message = "Your order is ready. Robot delivery has not started yet."
    else:
        message = "Your order is being prepared. Robot delivery has not started yet."

    return jsonify({
        "success": True,
        "tracking": {
            "order_id": order["id"],
            "status": status,
            "destination_table": order.get("table_number"),
            "position": position,
            "simulated": simulated,
            "message": message,
        },
    })


@app.route("/api/customer/orders/<order_id>", methods=["PUT"])
def edit_customer_order(order_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"success": False, "error": "A JSON order update is required."}), 400
    try:
        validated_items, total_cents, item_error = _validated_customer_order_items(
            data.get("items")
        )
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore menu configuration is not available: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, firebase_exceptions.FirebaseError):
        current_app.logger.exception("Could not read the Firestore menu before order edit.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    except MenuCatalogError:
        current_app.logger.exception("Could not validate the current menu for order edit.")
        return jsonify({
            "success": False,
            "error": "Menu data is temporarily unavailable. Please try again.",
        }), 503
    if item_error:
        return jsonify({"success": False, "error": item_error}), 400

    revision = data.get("revision")
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return jsonify({"success": False, "error": "A valid order revision is required."}), 400
    access_token = request.headers.get("X-Order-Access-Token", "")
    try:
        existing_order = get_authorized_customer_order(order_id, access_token)
        if existing_order is None:
            return jsonify({"success": False, "error": "Order not found."}), 404
        if existing_order["status"] != "Order Placed":
            return jsonify({
                "success": False,
                "error": "This order can no longer be edited.",
            }), 409
        order = update_customer_order(
            order_id,
            access_token,
            revision,
            {"items": validated_items, "total": total_cents / 100},
        )
    except OrderRevisionConflict as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not update customer order in Firestore.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Order not found."}), 404
    return jsonify({"success": True, "order": order})


@app.route("/api/customer/orders/<order_id>", methods=["DELETE"])
def cancel_customer_order(order_id):
    data = request.get_json(silent=True)
    revision = data.get("revision") if isinstance(data, dict) else None
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return jsonify({"success": False, "error": "A valid order revision is required."}), 400
    access_token = request.headers.get("X-Order-Access-Token", "")
    try:
        existing_order = get_authorized_customer_order(order_id, access_token)
        if existing_order is None:
            return jsonify({"success": False, "error": "Order not found."}), 404
        if existing_order["status"] not in {"Order Placed", "Accepted"}:
            return jsonify({
                "success": False,
                "error": "This order can no longer be cancelled.",
            }), 409
        order = update_customer_order(
            order_id,
            access_token,
            revision,
            {"status": "Cancelled"},
        )
    except OrderRevisionConflict as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not cancel customer order in Firestore.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Order not found."}), 404
    return jsonify({"success": True, "order": order})


@app.route("/api/admin/orders/<order_id>", methods=["PUT"])
def update_admin_customer_order_status(order_id):
    data = request.get_json(silent=True)
    status = data.get("status") if isinstance(data, dict) else None
    revision = data.get("revision") if isinstance(data, dict) else None
    allowed_statuses = {
        "Order Placed",
        "Accepted",
        "Preparing",
        "Ready",
        "Robot Delivery",
        "Completed",
        "Cancelled",
        "Failed",
    }
    if not isinstance(status, str) or status not in allowed_statuses:
        return jsonify({"success": False, "error": "Choose a valid order status."}), 400
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return jsonify({"success": False, "error": "A valid order revision is required."}), 400
    try:
        order = update_customer_order_status(order_id, revision, status)
    except OrderRevisionConflict as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except OrderStatusTransitionError as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not update customer order status in Firestore.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Order not found."}), 404
    return jsonify({"success": True, "order": order})


def _update_simulation_tracking(order, completed=False):
    table_number = order["table_number"]
    failed = order.get("status") == "Failed"
    with ROBOT_TRACKING_LOCK:
        ROBOT_TRACKING_STATE.update({
            "demo_mode": True,
            "source": "Firestore order simulation · not a physical robot",
            "controller_update_received": True,
            "status": (
                "SIMULATION COMPLETE"
                if completed
                else "SIMULATION FAILED"
                if failed
                else "SIMULATION DELIVERY"
            ),
            "current_position": (
                "COUNTER (SIMULATED)"
                if completed or failed
                else f"EN ROUTE TO TABLE {table_number}"
            ),
            "destination_table": table_number,
            "delivery_status": order["status"],
            "current_order_id": order["id"],
            "current_order_customer": order.get("customer_name"),
            "current_order_items": order.get("items", []),
            "current_order_total": order.get("total"),
            "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        })


def _simulation_delivery_allowed():
    environment_values = (
        os.environ.get("APP_ENV"),
        os.environ.get("FLASK_ENV"),
        app.config.get("APP_ENV"),
        app.config.get("FLASK_ENV"),
        app.config.get("ENV"),
    )
    return (
        app.config.get("SIMULATION_DELIVERY_ENABLED", True) is True
        and not any(
            isinstance(environment, str)
            and environment.strip().lower() == "production"
            for environment in environment_values
        )
    )


@app.route("/api/admin/simulation/orders", methods=["GET"])
def simulation_delivery_orders_api():
    try:
        orders = list_simulation_orders(limit=100)
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not load the simulation delivery queue.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    return jsonify({"success": True, **orders})


@app.route(
    "/api/admin/simulation/orders/<order_id>/claim",
    methods=["POST"],
)
def claim_simulation_delivery(order_id):
    if not _simulation_delivery_allowed():
        return jsonify({
            "success": False,
            "error": "Simulated delivery completion is disabled in production.",
        }), 403
    data = request.get_json(silent=True)
    mission_id = data.get("mission_id") if isinstance(data, dict) else None
    revision = data.get("revision") if isinstance(data, dict) else None
    if not isinstance(mission_id, str):
        return jsonify({"success": False, "error": "A simulation mission ID is required."}), 400
    try:
        mission_id = str(uuid.UUID(mission_id))
    except ValueError:
        return jsonify({"success": False, "error": "The simulation mission ID is invalid."}), 400
    if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
        return jsonify({"success": False, "error": "A valid order revision is required."}), 400
    try:
        order = claim_customer_order_for_simulation(
            order_id,
            revision,
            mission_id,
        )
    except OrderRevisionConflict as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except OrderStatusTransitionError as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not claim the simulation delivery order.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Eligible demo order not found."}), 404
    _update_simulation_tracking(order)
    return jsonify({"success": True, "order": order})


@app.route(
    "/api/admin/simulation/orders/<order_id>/complete",
    methods=["POST"],
)
def complete_simulation_delivery(order_id):
    if not _simulation_delivery_allowed():
        return jsonify({
            "success": False,
            "error": "Simulated delivery completion is disabled in production.",
        }), 403
    data = request.get_json(silent=True)
    mission_id = data.get("mission_id") if isinstance(data, dict) else None
    if not isinstance(mission_id, str):
        return jsonify({"success": False, "error": "A simulation mission ID is required."}), 400
    try:
        mission_id = str(uuid.UUID(mission_id))
    except ValueError:
        return jsonify({"success": False, "error": "The simulation mission ID is invalid."}), 400
    try:
        order = complete_customer_order_simulation(order_id, mission_id)
    except OrderStatusTransitionError as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not complete the simulation delivery order.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Eligible simulated order not found."}), 404
    _update_simulation_tracking(order, completed=True)
    return jsonify({"success": True, "order": order})


@app.route(
    "/api/admin/simulation/orders/<order_id>/position",
    methods=["POST"],
)
def update_simulation_delivery_position(order_id):
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({
            "success": False,
            "error": "A simulation position update is required.",
        }), 400

    mission_id = data.get("mission_id")
    if not isinstance(mission_id, str):
        return jsonify({
            "success": False,
            "error": "A simulation mission ID is required.",
        }), 400
    try:
        mission_id = str(uuid.UUID(mission_id))
    except ValueError:
        return jsonify({
            "success": False,
            "error": "The simulation mission ID is invalid.",
        }), 400

    x = data.get("x")
    z = data.get("z")
    moving = data.get("moving")
    if (
        isinstance(x, bool)
        or not isinstance(x, (int, float))
        or not math.isfinite(x)
        or not -30 <= x <= 30
        or isinstance(z, bool)
        or not isinstance(z, (int, float))
        or not math.isfinite(z)
        or not -30 <= z <= 30
        or not isinstance(moving, bool)
    ):
        return jsonify({
            "success": False,
            "error": "A valid simulated robot position is required.",
        }), 400

    try:
        order = update_customer_order_simulation_position(
            order_id,
            mission_id,
            x,
            z,
            moving,
        )
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({
            "success": False,
            "error": "Simulation tracking is temporarily unavailable.",
        }), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not publish simulation position.")
        return jsonify({
            "success": False,
            "error": "Simulation tracking is temporarily unavailable.",
        }), 503
    if order is None:
        return jsonify({
            "success": False,
            "error": "Active simulated delivery not found.",
        }), 404
    return jsonify({"success": True})


@app.route(
    "/api/admin/simulation/orders/<order_id>/fail",
    methods=["POST"],
)
def fail_simulation_delivery(order_id):
    data = request.get_json(silent=True)
    mission_id = data.get("mission_id") if isinstance(data, dict) else None
    if not isinstance(mission_id, str):
        return jsonify({"success": False, "error": "A simulation mission ID is required."}), 400
    try:
        mission_id = str(uuid.UUID(mission_id))
    except ValueError:
        return jsonify({"success": False, "error": "The simulation mission ID is invalid."}), 400
    try:
        order = fail_customer_order_simulation(order_id, mission_id)
    except OrderStatusTransitionError as error:
        return jsonify({"success": False, "error": str(error)}), 409
    except FirebaseConfigurationError as error:
        current_app.logger.error("Firestore order storage is not configured: %s", error)
        return jsonify({"success": False, "error": str(error)}), 503
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.error("Could not mark the simulation delivery as failed.")
        return jsonify({
            "success": False,
            "error": "Order storage is temporarily unavailable. Please try again.",
        }), 503
    if order is None:
        return jsonify({"success": False, "error": "Eligible simulated order not found."}), 404
    _update_simulation_tracking(order)
    return jsonify({"success": True, "order": order})

# =========================================================
# CUSTOMER PERSON DETECTION
# =========================================================

@app.route("/detect-customer", methods=["POST"])
def detect_customer():
    frame_file = request.files.get("frame")
    if frame_file is None:
        return jsonify({
            "success": False,
            "error": "A JPEG camera frame is required.",
        }), 400

    frame_bytes = frame_file.stream.read(MAX_CAMERA_FRAME_BYTES + 1)
    if not frame_bytes:
        return jsonify({
            "success": False,
            "error": "The uploaded camera frame is empty.",
        }), 400
    if len(frame_bytes) > MAX_CAMERA_FRAME_BYTES:
        return jsonify({
            "success": False,
            "error": "The camera frame exceeds the 5 MB limit.",
        }), 413

    try:
        import cv2
        import numpy as np
    except ModuleNotFoundError:
        app.logger.exception("Customer detection dependencies are missing.")
        return jsonify({
            "success": False,
            "error": (
                "Customer detection requires OpenCV and NumPy. "
                "Install the project dependencies and restart Flask."
            ),
        }), 503

    try:
        encoded_frame = np.frombuffer(frame_bytes, dtype=np.uint8)
        frame = cv2.imdecode(encoded_frame, cv2.IMREAD_COLOR)
    except cv2.error:
        frame = None

    if frame is None or frame.size == 0:
        return jsonify({
            "success": False,
            "error": "The uploaded frame is not a valid image.",
        }), 400

    frame_height, frame_width = frame.shape[:2]
    if frame_width > 4096 or frame_height > 4096:
        return jsonify({
            "success": False,
            "error": "The camera frame dimensions exceed 4096 by 4096 pixels.",
        }), 400

    try:
        cv2, detector = _get_person_detector()
    except (AttributeError, FileNotFoundError, cv2.error):
        app.logger.exception("Pretrained person detector could not be loaded.")
        return jsonify({
            "success": False,
            "error": (
                "The pretrained person detection model is unavailable. "
                "Check models/person_detection_mediapipe and restart Flask."
            ),
        }), 503

    try:
        results = detector.infer(frame)
    except cv2.error:
        app.logger.exception("OpenCV person detection failed.")
        return jsonify({
            "success": False,
            "error": "Person detection failed while processing the frame.",
        }), 500

    detections = []
    for result in results:
        x1, y1, x2, y2 = np.rint(result[:4]).astype(int)
        x1 = max(0, min(x1, frame_width))
        y1 = max(0, min(y1, frame_height))
        x2 = max(0, min(x2, frame_width))
        y2 = max(0, min(y2, frame_height))
        if x2 <= x1 or y2 <= y1:
            continue
        detections.append({
            "x": int(x1),
            "y": int(y1),
            "width": int(x2 - x1),
            "height": int(y2 - y1),
            "score": round(float(result[-1]), 3),
        })
    detected = bool(detections)

    return jsonify({
        "success": True,
        "detected": detected,
        "result": (
            "Customer Detected" if detected else "No Customer Detected"
        ),
        "detector": "MediaPipe person detector",
        "detections": detections,
        "frame_width": frame_width,
        "frame_height": frame_height,
    })

# =========================================================
# HEALTH CHECK
# =========================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({

        "status": "healthy",

        "project":
            "AI-Powered Natural Language Restaurant Service Robot",

        "modules": {

            "instruction_parser": True,

            "task_decomposer": True,

            "action_generator": True,

            "robot_controller": True,

            "failure_detector": True,

            "camera": True,

            "voice": True,

            "3d_simulation": True

        }

    })

# =========================================================
# PROCESS NATURAL LANGUAGE INSTRUCTION
# =========================================================

@app.route("/process", methods=["POST"])
def process_instruction():

    try:

        # -------------------------------------------------
        # GET REQUEST DATA
        # -------------------------------------------------

        data = request.get_json()

        if not data:

            return instruction_error(
                "No JSON data received.",
                "PROCESSING_ERROR"
            )

        instruction = data.get(
            "instruction",
            ""
        ).strip()

        if not instruction:

            return instruction_error(
                "Instruction is required.",
                "MISSING_INSTRUCTION"
            )

        print("\n" + "=" * 70)

        print(
            "RESTAURANT ROBOT INSTRUCTION:"
        )

        print(instruction)

        print("=" * 70)

        # -------------------------------------------------
        # STEP 1: INSTRUCTION PARSER
        # -------------------------------------------------

        parsed_instruction = parse_instruction(
            instruction
        )

        if not parsed_instruction:

            return instruction_error(
                "Instruction parsing failed.",
                "PROCESSING_ERROR"
            )

        if (
            parsed_instruction.get("intent") == "DELIVERY"
            and "orders" in parsed_instruction
        ):
            result, status_code = execute_delivery_orders(
                instruction,
                parsed_instruction,
            )
            return jsonify(result), status_code

        target = str(
            parsed_instruction.get(
                "target",
                ""
            )
        ).strip()
        table_match = re.fullmatch(
            r"table\s+(\d+)",
            target,
            flags=re.IGNORECASE
        )

        intent = parsed_instruction.get(
            "intent",
            ""
        )

        if (
            intent in {"DELIVERY", "NAVIGATE", "GUIDE"}
            and not table_match
        ):

            return instruction_error(
                "Please specify a destination table number.",
                "MISSING_DESTINATION"
            )

        if (
            intent == "DELIVERY"
            and not parsed_instruction.get("item")
            and not parsed_instruction.get("object")
        ):
            return instruction_error(
                "Please specify the items for delivery.",
                "MISSING_ITEMS"
            )

        if table_match:

            table_number = int(
                table_match.group(1)
            )

            if not 1 <= table_number <= 4:

                available_tables = "1, 2, 3, and 4"

                message = (
                    f"Table {table_number} does not exist. "
                    f"Available tables are {available_tables}. "
                    "Please select a valid table."
                )

                response, status_code = instruction_error(
                    message,
                    "INVALID_TABLE"
                )

                response_json = response.get_json()
                response_json["parser"] = parsed_instruction

                return jsonify(response_json), status_code

        print("\n[1] INSTRUCTION PARSER")

        print(parsed_instruction)

        # -------------------------------------------------
        # STEP 2: TASK DECOMPOSITION
        # -------------------------------------------------

        task_steps = decompose_task(
            parsed_instruction
        )

        if not task_steps:

            return instruction_error(
                "Task decomposition failed.",
                "PROCESSING_ERROR"
            )

        print("\n[2] TASK DECOMPOSITION")

        print(task_steps)

        # -------------------------------------------------
        # STEP 3: ACTION GENERATION
        # -------------------------------------------------

        action_objects = generate_action_sequence(
            task_steps
        )

        if not action_objects:

            return instruction_error(
                "Action generation failed.",
                "PROCESSING_ERROR"
            )

        print("\n[3] ACTION GENERATION")

        print(action_objects)

        # -------------------------------------------------
        # ROBOT COMMANDS
        # -------------------------------------------------

        robot_commands = [

            item["action"]

            for item in action_objects

        ]

        print("\n[4] ROBOT COMMANDS")

        print(robot_commands)

        # -------------------------------------------------
        # OBJECT INFORMATION
        # -------------------------------------------------

        color = parsed_instruction.get(
            "color",
            ""
        )

        obj = parsed_instruction.get(
            "object",
            ""
        )

        target = parsed_instruction.get(
            "target",
            ""
        )

        item = parsed_instruction.get(
            "item",
            ""
        )

        # -------------------------------------------------
        # FULL OBJECT NAME
        # -------------------------------------------------

        if color and obj:

            full_object_name = (
                f"{color} {obj}"
            )

        elif item:

            full_object_name = item

        else:

            full_object_name = obj

        # -------------------------------------------------
        # STEP 4: ROBOT CONTROLLER
        # -------------------------------------------------

        robot = RobotController()

        execution = robot.execute_sequence(

            robot_commands,

            object_name=
                full_object_name,

            target=
                target

        )

        print("\n[5] ROBOT EXECUTION")

        print(execution)

        # -------------------------------------------------
        # STEP 5: FAILURE DETECTION
        # -------------------------------------------------

        checked_results = []

        for result in execution.get(
            "results",
            []
        ):

            check = check_action(
                result
            )

            checked_results.append({

                "step":
                    result.get(
                        "step"
                    ),

                "command":
                    result.get(
                        "command"
                    ),

                "status":
                    result.get(
                        "status"
                    ),

                "attempts":
                    result.get(
                        "attempts",
                        1
                    ),

                "success":
                    check.get(
                        "success",
                        False
                    ),

                "message":
                    check.get(
                        "message",
                        ""
                    )

            })

        failure_analysis = analyze_execution(

            execution.get(
                "results",
                []
            )

        )

        print("\n[6] FAILURE ANALYSIS")

        print(failure_analysis)

        # -------------------------------------------------
        # FINAL RESPONSE
        # -------------------------------------------------

        overall_status = execution.get(

            "overall_status",

            "FAILED"

        )

        if overall_status == "SUCCESS":

            item_name = (
                full_object_name.strip()
                or "your item"
            )
            table_name = (
                target.strip()
                .title()
            )

            if intent == "DELIVERY":

                robot_response = (
                    "Your instruction is valid. Delivering the "
                    f"{item_name} to {table_name}."
                )

            elif intent == "NAVIGATE":

                robot_response = (
                    "Your instruction is valid. Navigating to "
                    f"{table_name}."
                )

            elif intent == "GUIDE":

                robot_response = (
                    "Your instruction is valid. Guiding the "
                    f"customer to {table_name}."
                )

            elif intent == "ORDER":

                robot_response = (
                    "Your instruction is valid. Your order for "
                    f"{item_name} has been confirmed."
                )

            else:

                robot_response = (
                    "Your instruction is valid and completed successfully."
                )

        else:

            robot_response = (
                "Sorry, I could not process your instruction. "
                "Please try again."
            )

        response = {

            "success":
                overall_status == "SUCCESS",

            "robot_response":
                robot_response,

            "instruction":
                instruction,

            "parser":
                parsed_instruction,

            "task_decomposition":
                task_steps,

            "action_sequence":
                action_objects,

            "robot_commands":
                robot_commands,

            "robot_execution":
                execution,

            "checked_execution":
                checked_results,

            "failure_analysis":
                failure_analysis,

            "overall_status":
                overall_status,

            "simulation": {

                "object":
                    full_object_name,

                "item":
                    item,

                "color":
                    color,

                "target":
                    target,

                "actions":
                    robot_commands

            }

        }

        print("\n" + "=" * 70)

        print(
            "FINAL STATUS:",
            overall_status
        )

        print("=" * 70)

        return jsonify(response)

    except Exception as e:

        print("\nERROR:")

        print(str(e))

        response, status_code = instruction_error(
            str(e),
            "PROCESSING_ERROR",
            500
        )

        return response, status_code

@app.route("/robot-tracking")
def robot_tracking():
    return render_template(
        "admin_dashboard/admin_robot_tracking.html",
        active_page="tracking",
        page_title="Robot Tracking",
        page_heading="Robot tracking",
        page_subtitle="A six-table floor map driven by the software-controller demo.",
    )


@app.route("/api/robot-tracking", methods=["GET"])
def robot_tracking_api():
    tracking_warning = None
    try:
        simulation_orders = [
            order
            for order in list_customer_orders(limit=100)
            if order.get("delivery_simulation_id")
        ]
        if simulation_orders:
            latest_order = max(
                simulation_orders,
                key=lambda order: str(
                    order.get("delivery_simulation_updated_at") or ""
                ),
            )
            _update_simulation_tracking(
                latest_order,
                completed=latest_order.get("status") == "Delivered",
            )
    except FirebaseConfigurationError as error:
        current_app.logger.warning(
            "Firestore is unavailable for robot tracking; using process-local simulation state: %s",
            error,
        )
        tracking_warning = (
            "Firestore is unavailable; showing only this worker's simulation state."
        )
    except (GoogleAPICallError, OrderPersistenceError):
        current_app.logger.exception(
            "Could not refresh robot tracking from Firestore."
        )
        tracking_warning = (
            "Firestore tracking refresh failed; displayed mission data may be stale."
        )

    with ROBOT_TRACKING_LOCK:
        state = dict(ROBOT_TRACKING_STATE)

    destination_table = state["destination_table"]
    tables = []
    for table_number in range(1, 7):
        status = "Available"
        if table_number == 2:
            status = "Occupied"
        elif table_number == 5:
            status = "Reserved"
        if table_number == destination_table:
            status = "Delivery target"
        tables.append({"table": table_number, "status": status})

    return jsonify({
        **state,
        "tables": tables,
        "tracking_warning": tracking_warning,
    })


# =========================================================
# START SERVER
# =========================================================

def _open_admin_login_when_ready(host, port, url):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.5):
                break
        except OSError:
            time.sleep(0.1)
    else:
        print(f"Flask did not become available; open {url} after the server starts.")
        return
    if not webbrowser.open(url, new=2):
        print(f"Could not open a browser automatically. Visit {url}")


if __name__ == "__main__":

    print("=" * 70)

    print(
        "🤖 AI RESTAURANT SERVICE ROBOT"
    )

    print("=" * 70)

    print()

    load_dotenv(Path(__file__).resolve().parent / ".env", override=False)
    configured_host, configured_port, debug_enabled = _server_startup_config()
    ssl_context = _server_ssl_context()
    _validate_server_transport(configured_host, ssl_context)
    scheme = "https" if ssl_context is not None else "http"
    browser_host = "127.0.0.1"
    admin_url = _admin_browser_url(configured_port, secure=ssl_context is not None)
    print("Health:")
    print(f"{scheme}://127.0.0.1:{configured_port}/health")
    print("=" * 70)
    print("Admin Login:")
    print(admin_url)
    if ssl_context is not None:
        print(
            "Customer checkout: "
            f"https://<computer-lan-ip>:{configured_port}/customer/menu"
            "?table=6"
        )
    if _should_open_admin_browser(debug_enabled):
        Thread(
            target=_open_admin_login_when_ready,
            args=(browser_host, configured_port, admin_url),
            daemon=True,
        ).start()
    app.run(
        host=configured_host,
        port=configured_port,
        debug=debug_enabled,
        ssl_context=ssl_context,
    )