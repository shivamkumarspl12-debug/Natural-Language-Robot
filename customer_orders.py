import hashlib
import hmac
import json
import math
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from firebase_admin import firestore
from google.api_core.exceptions import Conflict

from firebase_db import get_firestore_client


ORDER_COLLECTION = "customer_orders"
ORDER_ID_PATTERN = re.compile(r"QR-[A-F0-9]{32}")
SIMULATION_ACTIVE_STATUSES = {
    "Order Placed",
    "Accepted",
    "Preparing",
    "Ready",
}
_ORDER_STATUS_BY_NORMALIZED_VALUE = {
    status.casefold(): status
    for status in (
        "Order Placed",
        "Accepted",
        "Preparing",
        "Ready",
        "Robot Delivery",
        "Delivered",
        "Completed",
        "Cancelled",
        "Failed",
    )
}
_ORDER_STATUS_BY_NORMALIZED_VALUE["received by flask demo"] = "Order Placed"


class OrderIdempotencyConflict(ValueError):
    pass


class OrderPersistenceError(RuntimeError):
    pass


class CustomerIdentityConfigurationError(RuntimeError):
    pass


def _order_collection():
    return get_firestore_client().collection(ORDER_COLLECTION)


def customer_identity_for_phone(phone_digits):
    key = os.environ.get("CUSTOMER_ID_HMAC_KEY", "")
    if not key:
        return None
    key_bytes = key.encode("utf-8")
    if len(key_bytes) < 32:
        raise CustomerIdentityConfigurationError(
            "CUSTOMER_ID_HMAC_KEY must contain at least 32 bytes."
        )
    return hmac.new(
        key_bytes,
        phone_digits.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _request_fingerprint(order):
    fingerprint_order = {
        key: value
        for key, value in order.items()
        if key not in {"revision", "status_updated_at"}
    }
    serialized = json.dumps(
        fingerprint_order,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _serialize_order(order, include_private=False):
    serialized = dict(order)
    serialized.pop("_request_fingerprint", None)
    serialized.pop("order_access_token_hash", None)
    if not include_private:
        serialized.pop("customer_identity", None)
    for field in (
        "created_at",
        "status_updated_at",
        "delivery_simulation_updated_at",
    ):
        value = serialized.get(field)
        if isinstance(value, datetime):
            serialized[field] = value.isoformat(timespec="seconds")
    return serialized


def normalize_order_status(status):
    if not isinstance(status, str):
        return None
    normalized_value = " ".join(status.split()).casefold()
    return _ORDER_STATUS_BY_NORMALIZED_VALUE.get(normalized_value)


def save_customer_order(order, idempotency_key=None):
    fingerprint = _request_fingerprint(order)
    if idempotency_key:
        order_token = hashlib.sha256(
            idempotency_key.encode("utf-8")
        ).hexdigest()[:32].upper()
    else:
        order_token = uuid.uuid4().hex.upper()

    order_id = f"QR-{order_token}"
    document = _order_collection().document(order_id)
    stored_order = {
        **order,
        "id": order_id,
        "created_at": firestore.SERVER_TIMESTAMP,
        "_request_fingerprint": fingerprint,
    }

    try:
        write_result = document.create(stored_order)
    except Conflict:
        snapshot = document.get()
        existing_order = snapshot.to_dict()
        if existing_order is None:
            raise OrderPersistenceError(
                "Firestore reported an existing order but returned no record."
            ) from None
        if existing_order.get("_request_fingerprint") != fingerprint:
            raise OrderIdempotencyConflict(
                "This checkout request key was already used for a different order."
            ) from None
        return _serialize_order(existing_order)

    stored_order["created_at"] = write_result.update_time
    return _serialize_order(stored_order)


def get_customer_order(order_id):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None

    snapshot = _order_collection().document(order_id).get()
    order = snapshot.to_dict()
    return _serialize_order(order) if order is not None else None


def get_authorized_customer_order(order_id, access_token):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    if not isinstance(access_token, str) or not access_token:
        return None
    order = _order_collection().document(order_id).get().to_dict()
    if order is None:
        return None
    stored_token_hash = order.get("order_access_token_hash", "")
    token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    if not isinstance(stored_token_hash, str) or not hmac.compare_digest(
        stored_token_hash,
        token_hash,
    ):
        return None
    return _serialize_order(order)


def update_customer_order(
    order_id,
    access_token,
    expected_revision,
    updates,
):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    if not isinstance(access_token, str) or not access_token:
        return None

    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    token_hash = hashlib.sha256(access_token.encode("utf-8")).hexdigest()
    transaction = client.transaction()

    @firestore.transactional
    def apply_update(transaction):
        snapshot = document.get(transaction=transaction)
        order = snapshot.to_dict()
        if order is None:
            return None
        stored_token_hash = order.get("order_access_token_hash", "")
        if not isinstance(stored_token_hash, str) or not hmac.compare_digest(
            stored_token_hash,
            token_hash,
        ):
            return False
        revision = order.get("revision", 0)
        if revision != expected_revision:
            raise OrderRevisionConflict(
                "This order changed. Refresh it before trying again."
            )

        updated_order = {
            **order,
            **updates,
            "revision": revision + 1,
            "status_updated_at": datetime.now(timezone.utc),
        }
        transaction.update(document, {
            **updates,
            "revision": revision + 1,
            "status_updated_at": updated_order["status_updated_at"],
        })
        return _serialize_order(updated_order)

    return apply_update(transaction)


def update_customer_order_status(order_id, expected_revision, status):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    transaction = client.transaction()

    @firestore.transactional
    def apply_update(transaction):
        snapshot = document.get(transaction=transaction)
        order = snapshot.to_dict()
        if order is None:
            return None
        revision = order.get("revision", 0)
        if revision != expected_revision:
            raise OrderRevisionConflict(
                "This order changed. Refresh it before trying again."
            )
        current_status = order.get("status")
        normalized_current_status = normalize_order_status(current_status)
        if normalized_current_status == status:
            return _serialize_order(order)
        if normalized_current_status in {
            "Completed",
            "Delivered",
            "Cancelled",
            "Failed",
        }:
            raise OrderStatusTransitionError(
                "Order status cannot change from terminal state "
                f"{normalized_current_status}."
            )
        next_status = {
            "Order Placed": "Accepted",
            "Accepted": "Preparing",
            "Preparing": "Ready",
            "Ready": None,
        }.get(normalized_current_status)
        allowed_statuses = {next_status, "Failed"}
        if normalized_current_status != "Robot Delivery":
            allowed_statuses.add("Cancelled")
        if status not in allowed_statuses:
            raise OrderStatusTransitionError(
                f"Order status cannot change from {current_status} to {status}."
            )
        updated_at = datetime.now(timezone.utc)
        updated_order = {
            **order,
            "status": status,
            "revision": revision + 1,
            "status_updated_at": updated_at,
        }
        transaction.update(document, {
            "status": status,
            "revision": revision + 1,
            "status_updated_at": updated_at,
        })
        return _serialize_order(updated_order)

    return apply_update(transaction)


def _is_simulation_order_valid(order):
    table_number = order.get("table_number")
    items = order.get("items")
    if (
        order.get("demo_only") is not True
        or not isinstance(order.get("customer_name"), str)
        or not order["customer_name"].strip()
        or not isinstance(table_number, int)
        or isinstance(table_number, bool)
        or not 1 <= table_number <= 6
        or not isinstance(items, list)
        or not items
    ):
        return False
    for item in items:
        quantity = item.get("quantity") if isinstance(item, dict) else None
        if (
            not isinstance(item, dict)
            or not isinstance(item.get("name"), str)
            or not item["name"].strip()
            or isinstance(quantity, bool)
            or not isinstance(quantity, int)
            or quantity < 1
        ):
            return False
    try:
        total = float(order.get("total"))
    except (TypeError, ValueError, OverflowError):
        return False
    return total >= 0 and math.isfinite(total)


def list_simulation_orders(limit=100):
    ready_orders = []
    pending_orders = []
    for order in list_customer_orders(limit=limit):
        status = normalize_order_status(order.get("status"))
        if (
            not _is_simulation_order_valid(order)
            or status not in SIMULATION_ACTIVE_STATUSES
        ):
            continue
        visible_order = {**order, "status": status}
        if status == "Ready":
            visible_order["delivery_eligible"] = True
            ready_orders.append(visible_order)
        else:
            visible_order["delivery_eligible"] = False
            pending_orders.append(visible_order)
    return {
        "orders": ready_orders,
        "pending_orders": pending_orders,
    }


def claim_customer_order_for_simulation(order_id, expected_revision, mission_id):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    transaction = client.transaction()

    @firestore.transactional
    def claim(transaction):
        order = document.get(transaction=transaction).to_dict()
        if order is None or not _is_simulation_order_valid(order):
            return None
        if (
            order.get("status") == "Robot Delivery"
            and order.get("delivery_simulation_id") == mission_id
        ):
            return _serialize_order(order)
        if normalize_order_status(order.get("status")) != "Ready":
            raise OrderStatusTransitionError(
                "Only ready demo orders can enter simulated robot delivery."
            )
        if order.get("revision", 0) != expected_revision:
            raise OrderRevisionConflict(
                "This order changed. Refresh the simulation queue and try again."
            )
        updated_at = datetime.now(timezone.utc)
        updates = {
            "status": "Robot Delivery",
            "delivery_simulation_id": mission_id,
            "delivery_simulation_state": "in_progress",
            "delivery_simulation_updated_at": updated_at,
            "delivery_simulation_position": {
                "x": -11.0,
                "z": -7.0,
                "moving": False,
                "updated_at": updated_at,
            },
            "revision": expected_revision + 1,
            "status_updated_at": updated_at,
        }
        transaction.update(document, updates)
        return _serialize_order({**order, **updates})

    return claim(transaction)


def update_customer_order_simulation_position(
    order_id,
    mission_id,
    x,
    z,
    moving,
):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    transaction = client.transaction()

    @firestore.transactional
    def update_position(transaction):
        order = document.get(transaction=transaction).to_dict()
        if (
            order is None
            or order.get("demo_only") is not True
            or order.get("status") != "Robot Delivery"
            or order.get("delivery_simulation_id") != mission_id
            or order.get("delivery_simulation_state") != "in_progress"
        ):
            return None
        updated_at = datetime.now(timezone.utc)
        position = {
            "x": float(x),
            "z": float(z),
            "moving": moving,
            "updated_at": updated_at,
        }
        transaction.update(document, {
            "delivery_simulation_position": position,
            "delivery_simulation_updated_at": updated_at,
        })
        return _serialize_order({
            **order,
            "delivery_simulation_position": position,
            "delivery_simulation_updated_at": updated_at,
        })

    return update_position(transaction)


def complete_customer_order_simulation(order_id, mission_id):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    transaction = client.transaction()

    @firestore.transactional
    def complete(transaction):
        order = document.get(transaction=transaction).to_dict()
        if order is None or order.get("demo_only") is not True:
            return None
        if (
            order.get("status") == "Delivered"
            and order.get("delivery_simulation_id") == mission_id
            and order.get("delivery_simulation_state") == "delivered"
        ):
            return _serialize_order(order)
        if (
            order.get("status") != "Robot Delivery"
            or order.get("delivery_simulation_id") != mission_id
            or order.get("delivery_simulation_state") != "in_progress"
        ):
            raise OrderStatusTransitionError(
                "This simulated delivery is not active or has already ended."
            )
        updated_at = datetime.now(timezone.utc)
        updates = {
            "status": "Delivered",
            "delivery_simulation_state": "delivered",
            "delivery_simulation_updated_at": updated_at,
            "revision": order.get("revision", 0) + 1,
            "status_updated_at": updated_at,
        }
        transaction.update(document, updates)
        return _serialize_order({**order, **updates})

    return complete(transaction)


def fail_customer_order_simulation(order_id, mission_id):
    if not ORDER_ID_PATTERN.fullmatch(order_id):
        return None
    client = get_firestore_client()
    document = client.collection(ORDER_COLLECTION).document(order_id)
    transaction = client.transaction()

    @firestore.transactional
    def fail(transaction):
        order = document.get(transaction=transaction).to_dict()
        if order is None or order.get("demo_only") is not True:
            return None
        if (
            order.get("status") == "Failed"
            and order.get("delivery_simulation_id") == mission_id
            and order.get("delivery_simulation_state") == "failed"
        ):
            return _serialize_order(order)
        if (
            order.get("status") != "Robot Delivery"
            or order.get("delivery_simulation_id") != mission_id
            or order.get("delivery_simulation_state") != "in_progress"
        ):
            raise OrderStatusTransitionError(
                "This simulated delivery cannot be marked failed."
            )
        updated_at = datetime.now(timezone.utc)
        updates = {
            "status": "Failed",
            "delivery_simulation_state": "failed",
            "delivery_simulation_updated_at": updated_at,
            "revision": order.get("revision", 0) + 1,
            "status_updated_at": updated_at,
        }
        transaction.update(document, updates)
        return _serialize_order({**order, **updates})

    return fail(transaction)


def list_customer_orders(limit=200, include_private=False):
    collection = _order_collection()
    if limit is None:
        snapshots = collection.stream()
    else:
        snapshots = (
            collection
            .order_by("created_at", direction="DESCENDING")
            .limit(limit)
            .stream()
        )
    orders = []
    for snapshot in snapshots:
        order = snapshot.to_dict()
        if order is not None:
            orders.append(_serialize_order(order, include_private=include_private))
    return orders


class OrderRevisionConflict(ValueError):
    pass


class OrderStatusTransitionError(ValueError):
    pass


def _parse_order_time(value):
    if isinstance(value, datetime):
        created_at = value
    elif isinstance(value, str):
        try:
            created_at = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None

    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=timezone.utc)
    return created_at.astimezone(timezone.utc)


def _amount_in_cents(value):
    try:
        amount = Decimal(str(value)).quantize(
            Decimal("0.01"),
            rounding=ROUND_HALF_UP,
        )
    except (InvalidOperation, ValueError):
        return 0
    if not amount.is_finite() or amount < 0:
        return 0
    return int(amount * 100)


def aggregate_customer_orders(orders, now=None):
    current_time = now or datetime.now(timezone.utc)
    if current_time.tzinfo is None:
        current_time = current_time.replace(tzinfo=timezone.utc)
    current_time = current_time.astimezone(timezone.utc)
    cutoff = current_time.timestamp() - 7 * 24 * 60 * 60

    customers = {}
    seen_order_ids = set()
    for index, order in enumerate(orders):
        if not isinstance(order, dict):
            continue
        order_id = str(order.get("id") or f"untracked-{index}")
        if order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)

        identity = order.get("customer_identity")
        identity_available = isinstance(identity, str) and bool(identity)
        customer_key = (
            f"phone:{identity}"
            if identity_available
            else f"unidentified:{order_id}"
        )
        customer = customers.setdefault(customer_key, {
            "id": identity if identity_available else f"unidentified-{order_id}",
            "identity_available": identity_available,
            "name": "",
            "phone_last4": "",
            "order_count": 0,
            "spending_cents": 0,
            "first_order_at": None,
            "last_order_at": None,
            "orders": [],
        })

        created_at = _parse_order_time(order.get("created_at"))
        order_record = {
            "id": order_id,
            "created_at": created_at.isoformat() if created_at else None,
            "table_number": order.get("table_number"),
            "total": _amount_in_cents(order.get("total")) / 100,
            "items": [
                {
                    "name": item.get("name", item.get("id", "Item")),
                    "quantity": item.get("quantity", 1),
                }
                for item in (
                    order.get("items")
                    if isinstance(order.get("items"), list)
                    else []
                )
                if isinstance(item, dict)
            ],
        }
        customer["orders"].append(order_record)
        customer["order_count"] += 1
        customer["spending_cents"] += _amount_in_cents(order.get("total"))

        if created_at is not None:
            if (
                customer["first_order_at"] is None
                or created_at < customer["first_order_at"]
            ):
                customer["first_order_at"] = created_at
            if (
                customer["last_order_at"] is None
                or created_at > customer["last_order_at"]
            ):
                customer["last_order_at"] = created_at
                customer["name"] = str(order.get("customer_name") or "Customer")
                customer["phone_last4"] = str(order.get("phone_last4") or "")
        elif not customer["name"]:
            customer["name"] = str(order.get("customer_name") or "Customer")
            customer["phone_last4"] = str(order.get("phone_last4") or "")

    summaries = []
    total_orders = 0
    total_spending_cents = 0
    returning_customers = 0
    new_customers_this_week = 0
    for customer in customers.values():
        customer["orders"].sort(
            key=lambda order: order["created_at"] or "",
            reverse=True,
        )
        customer["first_order_at"] = (
            customer["first_order_at"].isoformat()
            if customer["first_order_at"]
            else None
        )
        customer["last_order_at"] = (
            customer["last_order_at"].isoformat()
            if customer["last_order_at"]
            else None
        )
        customer["total_spending"] = customer.pop("spending_cents") / 100
        customer["phone"] = (
            f"Unmatched · •••• {customer.pop('phone_last4')}"
            if not customer["identity_available"] and customer["phone_last4"]
            else (
                f"•••• {customer.pop('phone_last4')}"
                if customer["phone_last4"]
                else "Identity unavailable"
            )
        )
        customer["orders_history"] = customer.pop("orders")
        total_orders += customer["order_count"]
        total_spending_cents += round(customer["total_spending"] * 100)
        returning_customers += customer["order_count"] > 1
        first_order_at = _parse_order_time(customer["first_order_at"])
        new_customers_this_week += bool(
            first_order_at and first_order_at.timestamp() >= cutoff
        )
        summaries.append(customer)

    summaries.sort(
        key=lambda customer: customer["last_order_at"] or "",
        reverse=True,
    )
    customer_count = len(summaries)
    return {
        "summary": {
            "total_customers": customer_count,
            "returning_rate_percent": (
                round(returning_customers * 100 / customer_count)
                if customer_count
                else 0
            ),
            "average_order_spend": (
                (
                    total_spending_cents + total_orders // 2
                ) // total_orders / 100
                if total_orders
                else 0
            ),
            "new_customers_this_week": new_customers_this_week,
            "total_orders": total_orders,
        },
        "customers": summaries,
    }
