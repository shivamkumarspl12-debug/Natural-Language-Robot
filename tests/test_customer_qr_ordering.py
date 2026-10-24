import base64
from io import BytesIO
import os
import unittest
from unittest.mock import patch

from PIL import Image
from werkzeug.middleware.proxy_fix import ProxyFix

import app as app_module
from firestore_fakes import MemoryFirestore


class CustomerQrOrderingTests(unittest.TestCase):

    def setUp(self):
        app_module.app.config["TESTING"] = True
        app_module.app.config["FIREBASE_ADMIN_UIDS"] = {"test-admin"}
        app_module.PUBLIC_DEMO_ORDER_ATTEMPTS.clear()
        self.client = app_module.app.test_client()
        self.client.set_cookie("admin_session", "test-session")
        self.auth_patch = patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "test-admin"},
        )
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "customer_orders.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)
        seeded_menu = self.client.get("/api/admin/menu")
        self.assertEqual(seeded_menu.status_code, 200)

    def post_order(self, payload):
        return self.client.post(
            "/api/customer/orders",
            json=payload,
            headers={
                "Origin": "http://localhost",
                "X-Order-Access-Token": "Q" * 43,
            },
        )

    def test_customer_pages_render_and_preserve_a_valid_table(self):
        for table_number in range(1, 7):
            response = self.client.get(
                f"/customer/menu?table={table_number}"
            )
            self.assertEqual(response.status_code, 200)
            self.assertIn(
                f'data-table-number="{table_number}"'.encode(),
                response.data,
            )
            checkout = self.client.get(
                f"/customer/checkout?table={table_number}"
            )
            self.assertEqual(checkout.status_code, 200)
            self.assertIn(
                f'data-table-number="{table_number}"'.encode(),
                checkout.data,
            )

        paths = [
            "/customer/cart?table=6",
            "/customer/checkout?table=6",
            "/customer/order-status?table=6",
            "/customer/my-orders?table=6",
        ]
        for path in paths:
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)
                self.assertIn(b'data-table-number="6"', response.data)

        menu = self.client.get("/customer/menu?table=6")
        self.assertIn(b'href="/customer/my-orders?table=6"', menu.data)
        self.assertIn(b'href="/customer/robot-tracking?table=6"', menu.data)
        self.assertNotIn(b'href="/simulation"', menu.data)

    def test_customer_menu_rejects_a_table_outside_the_configured_set(self):
        response = self.client.get("/customer/menu?table=7")

        self.assertEqual(response.status_code, 400)

    def test_order_requires_valid_table_and_uses_server_catalog_prices(self):
        payload = {
            "customer_name": "Jordan Guest",
            "customer_phone": "5035550188",
            "table_number": 6,
            "items": [{"id": "garden-margherita", "quantity": 2}],
        }
        response = self.post_order(payload)

        self.assertEqual(response.status_code, 201)
        order = response.get_json()["order"]
        self.assertEqual(order["table_number"], 6)
        self.assertEqual(order["total"], 37.0)
        self.assertTrue(order["demo_only"])
        self.assertEqual(
            len(self.database.collections["customer_orders"]),
            1,
        )

        payload["table_number"] = 9
        invalid = self.client.post(
            "/api/customer/orders",
            json=payload,
            headers={"Origin": "http://localhost"},
        )
        self.assertEqual(invalid.status_code, 400)

    def test_order_submission_accepts_each_supported_table(self):
        for table_number in range(1, 7):
            with self.subTest(table_number=table_number):
                response = self.client.post(
                    "/api/customer/orders",
                    json={
                        "customer_name": "Jordan Guest",
                        "customer_phone": "5035550188",
                        "table_number": table_number,
                        "items": [
                            {"id": "garden-margherita", "quantity": 1}
                        ],
                    },
                    headers={
                        "Origin": "https://192.0.2.10:5000",
                        "X-Order-Access-Token": "Q" * 43,
                        "Idempotency-Key": f"qr-table-order-{table_number}",
                    },
                    base_url="https://192.0.2.10:5000",
                )

                self.assertEqual(response.status_code, 201)
                self.assertEqual(
                    response.get_json()["order"]["table_number"],
                    table_number,
                )

    def test_https_checkout_and_order_submission_use_same_origin(self):
        base_url = "https://192.0.2.10:5000"
        checkout = self.client.get(
            "/customer/checkout?table=1",
            base_url=base_url,
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )
        self.assertEqual(checkout.status_code, 200)
        self.assertIn(b'id="checkoutForm"', checkout.data)

        response = self.client.post(
            "/api/customer/orders",
            json={
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 1,
                "items": [{"id": "garden-margherita", "quantity": 1}],
            },
            headers={
                "Origin": base_url,
                "X-Order-Access-Token": "Q" * 43,
                "Idempotency-Key": "https-checkout-order-001",
            },
            base_url=base_url,
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )

        self.assertEqual(response.status_code, 201)
        self.assertTrue(response.get_json()["success"])
        self.assertEqual(
            len(self.database.collections["customer_orders"]),
            1,
        )

    def test_customer_order_rejects_cross_origin_csrf_request(self):
        response = self.client.post(
            "/api/customer/orders",
            json={
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 1,
                "items": [{"id": "garden-margherita", "quantity": 1}],
            },
            headers={
                "Origin": "https://attacker.example",
                "X-Order-Access-Token": "Q" * 43,
            },
            base_url="https://192.0.2.10:5000",
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn("could not be verified", response.get_json()["error"])
        self.assertFalse(self.database.collections.get("customer_orders"))

    def test_customer_order_requires_access_token(self):
        payload = {
            "customer_name": "Jordan Guest",
            "customer_phone": "5035550188",
            "table_number": 6,
            "items": [{"id": "garden-margherita", "quantity": 1}],
        }
        missing_token = self.client.post(
            "/api/customer/orders",
            json=payload,
            headers={
                "Origin": "http://localhost",
                "Idempotency-Key": "private-access-check-001",
            },
        )
        self.assertEqual(missing_token.status_code, 400)
        self.assertIn("access token is required", missing_token.get_json()["error"])
        self.assertFalse(self.database.collections.get("customer_orders"))

        invalid_token = self.client.post(
            "/api/customer/orders",
            json=payload,
            headers={
                "Origin": "http://localhost",
                "X-Order-Access-Token": "invalid",
            },
        )
        self.assertEqual(invalid_token.status_code, 400)
        self.assertIn("valid order access token", invalid_token.get_json()["error"])
        self.assertFalse(self.database.collections.get("customer_orders"))

    def test_unavailable_items_are_rejected_by_backend(self):
        response = self.client.post(
            "/api/customer/orders",
            json={
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 2,
                "items": [{"id": "dark-chocolate-mousse", "quantity": 1}],
            },
            headers={"Origin": "http://localhost"},
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("unavailable", response.get_json()["error"])

    def test_admin_orders_shows_received_qr_demo_order(self):
        created = self.post_order({
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 6,
                "items": [{"id": "garden-margherita", "quantity": 1}],
            })
        self.assertEqual(created.status_code, 201)

        response = self.client.get("/admin/orders")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"QR table orders", response.data)
        self.assertIn(b"Jordan Guest", response.data)
        self.assertIn(b"Table 6", response.data)

    def test_admin_tables_generates_six_qrs_from_configured_lan_url(self):
        with patch.dict(
            os.environ,
            {"CUSTOMER_QR_BASE_URL": "http://192.0.2.24:5000"},
        ), patch(
            "app.qrcode.make",
            wraps=app_module.qrcode.make,
        ) as make_qr:
            response = self.client.get(
                "/admin/tables",
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 200)
        for table_number in range(1, 7):
            expected_url = (
                f"https://192.0.2.24:5000/customer/menu?table={table_number}"
            )
            self.assertIn(
                expected_url.encode(),
                response.data,
            )
            make_qr.assert_any_call(expected_url)
        self.assertEqual(make_qr.call_count, 6)
        self.assertEqual(response.data.count(b'class="table-qr-image"'), 6)
        self.assertNotIn(b"localhost", response.data.lower())

        image_data = app_module._customer_qr_image_data(
            "https://192.0.2.24:5000/customer/menu?table=1"
        )
        image_bytes = base64.b64decode(image_data.split(",", 1)[1])
        with Image.open(BytesIO(image_bytes)) as image:
            self.assertEqual(image.format, "PNG")
            self.assertGreater(image.width, 0)

    def test_loopback_host_generates_labeled_local_demo_qrs(self):
        self.client.set_cookie(
            "admin_session",
            "test-session",
            domain="127.0.0.1",
        )
        with patch.dict(os.environ, {"CUSTOMER_QR_BASE_URL": ""}):
            response = self.client.get(
                "/admin/tables",
                base_url="http://127.0.0.1:5000",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Local demo QR codes only", response.data)
        self.assertEqual(response.data.count(b'class="table-qr-image"'), 6)
        for table_number in range(1, 7):
            expected_url = (
                f"http://127.0.0.1:5000/customer/menu?table={table_number}"
            )
            self.assertIn(expected_url.encode(), response.data)

    def test_loopback_http_does_not_use_configured_nonlocal_qr_url(self):
        self.client.set_cookie(
            "admin_session",
            "test-session",
            domain="127.0.0.1",
        )
        with patch.dict(
            os.environ,
            {"CUSTOMER_QR_BASE_URL": "https://demo.example.test"},
        ):
            response = self.client.get(
                "/admin/tables",
                base_url="http://127.0.0.1:5000",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Local demo QR codes only", response.data)

    def test_local_admin_generates_all_six_public_demo_qrs(self):
        self.client.set_cookie(
            "admin_session",
            "test-session",
            domain="127.0.0.1",
        )
        public_url = "https://demo-123.trycloudflare.com"
        with patch.dict(os.environ, {
            "PUBLIC_DEMO_MODE": "1",
            "PUBLIC_DEMO_URL": public_url,
            "QR_BASE_URL": public_url,
        }):
            response = self.client.get(
                "/admin/tables",
                base_url="http://127.0.0.1:5000",
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Temporary public demo QR codes", response.data)
        self.assertNotIn(b"Local demo QR codes only", response.data)
        self.assertIn(b"Working QR codes", response.data)
        self.assertIn(b"QR destination", response.data)
        self.assertEqual(response.data.count(b'class="table-qr-image"'), 6)
        for table_number in range(1, 7):
            self.assertIn(
                (
                    f"{public_url}/customer/menu?table={table_number}"
                ).encode(),
                response.data,
            )

    def test_public_demo_allows_customer_routes_but_blocks_admin_and_robot(self):
        public_url = "https://demo-123.trycloudflare.com"
        allowed_routes = [
            ("/customer/menu?table=1", "GET"),
            ("/customer/cart?table=1", "GET"),
            ("/customer/checkout?table=1", "GET"),
            ("/customer/my-orders?table=1", "GET"),
            ("/customer/order-status?table=1", "GET"),
            ("/api/customer/menu", "GET"),
            ("/static/css/customer.css", "GET"),
            ("/static/js/customer.js", "GET"),
        ]
        blocked_routes = [
            "/admin",
            "/admin/tables",
            "/api/admin/menu",
            "/api/admin/analytics",
            "/health",
            "/simulation",
            "/api/admin/simulation/orders",
            "/api/customer/orders/QR-123/tracking",
            "/customer/robot-tracking",
        ]
        with patch.dict(os.environ, {
            "PUBLIC_DEMO_MODE": "1",
            "PUBLIC_DEMO_URL": public_url,
            "QR_BASE_URL": public_url,
        }):
            for path, method in allowed_routes:
                with self.subTest(path=path):
                    response = self.client.open(
                        path,
                        method=method,
                        base_url=public_url,
                        environ_base={"REMOTE_ADDR": "127.0.0.1"},
                        headers={"CF-Connecting-IP": "203.0.113.9"},
                    )
                    self.assertNotEqual(response.status_code, 404)
                    self.assertNotEqual(response.status_code, 405)
                    response.close()

            for path in blocked_routes:
                with self.subTest(path=path):
                    response = self.client.get(
                        path,
                        base_url=public_url,
                        environ_base={"REMOTE_ADDR": "127.0.0.1"},
                        headers={"CF-Connecting-IP": "203.0.113.9"},
                    )
                    self.assertEqual(response.status_code, 404)
                    response.close()

    def test_public_demo_trusts_only_the_local_proxy_connection(self):
        public_url = "https://demo-123.trycloudflare.com"
        original_wsgi_app = app_module.app.wsgi_app
        app_module.app.wsgi_app = ProxyFix(
            original_wsgi_app,
            x_for=1,
            x_proto=1,
            x_host=1,
        )
        try:
            proxy_client = app_module.app.test_client()
            with patch.dict(os.environ, {
                "PUBLIC_DEMO_MODE": "1",
                "PUBLIC_DEMO_URL": public_url,
                "QR_BASE_URL": public_url,
            }):
                allowed = proxy_client.get(
                    "/customer/menu?table=1",
                    base_url="http://127.0.0.1:5000",
                    environ_base={"REMOTE_ADDR": "127.0.0.1"},
                    headers={
                        "X-Forwarded-For": "203.0.113.9",
                        "X-Forwarded-Proto": "https",
                        "X-Forwarded-Host": "demo-123.trycloudflare.com",
                        "CF-Connecting-IP": "203.0.113.9",
                    },
                )
                self.assertEqual(allowed.status_code, 200)
                self.assertIn(b'data-table-number="1"', allowed.data)
                allowed.close()

                blocked = proxy_client.get(
                    "/admin",
                    base_url="http://127.0.0.1:5000",
                    environ_base={"REMOTE_ADDR": "127.0.0.1"},
                    headers={
                        "X-Forwarded-For": "203.0.113.9",
                        "X-Forwarded-Proto": "https",
                        "X-Forwarded-Host": "demo-123.trycloudflare.com",
                        "CF-Connecting-IP": "203.0.113.9",
                    },
                )
                self.assertEqual(blocked.status_code, 404)
                blocked.close()

                direct = proxy_client.get(
                    "/customer/menu?table=1",
                    base_url=public_url,
                    environ_base={"REMOTE_ADDR": "203.0.113.9"},
                    headers={"CF-Connecting-IP": "203.0.113.9"},
                )
                self.assertEqual(direct.status_code, 404)
                direct.close()
        finally:
            app_module.app.wsgi_app = original_wsgi_app

    def test_public_demo_requires_cloudflare_client_ip_and_limits_orders(self):
        public_url = "https://demo-123.trycloudflare.com"
        payload = {
            "customer_name": "Jordan Guest",
            "customer_phone": "5035550188",
            "table_number": 1,
            "items": [{"id": "garden-margherita", "quantity": 1}],
        }
        with patch.dict(os.environ, {
            "PUBLIC_DEMO_MODE": "1",
            "PUBLIC_DEMO_URL": public_url,
            "QR_BASE_URL": public_url,
        }):
            missing_ip = self.client.post(
                "/api/customer/orders",
                json=payload,
                base_url=public_url,
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
                headers={
                    "Origin": public_url,
                    "X-Order-Access-Token": "Q" * 43,
                    "Idempotency-Key": "public-demo-without-client-ip",
                },
            )
            self.assertEqual(missing_ip.status_code, 429)

            response = None
            for attempt in range(app_module.PUBLIC_DEMO_ORDER_LIMIT):
                response = self.client.post(
                    "/api/customer/orders",
                    json=payload,
                    base_url=public_url,
                    environ_base={"REMOTE_ADDR": "127.0.0.1"},
                    headers={
                        "Origin": public_url,
                        "CF-Connecting-IP": "203.0.113.9",
                        "X-Order-Access-Token": "Q" * 43,
                        "Idempotency-Key": f"public-demo-order-{attempt}",
                    },
                )
                self.assertEqual(response.status_code, 201)

            limited = self.client.post(
                "/api/customer/orders",
                json=payload,
                base_url=public_url,
                environ_base={"REMOTE_ADDR": "127.0.0.1"},
                headers={
                    "Origin": public_url,
                    "CF-Connecting-IP": "203.0.113.9",
                    "X-Order-Access-Token": "Q" * 43,
                    "Idempotency-Key": "public-demo-order-limit",
                },
            )
            self.assertEqual(limited.status_code, 429)

    def test_dotenv_configuration_is_loaded_when_rendering_qrs(self):
        with (
            patch.dict(os.environ, {"CUSTOMER_QR_BASE_URL": ""}),
            patch(
                "app.load_dotenv",
                side_effect=lambda *_args, **_kwargs: os.environ.update({
                    "CUSTOMER_QR_BASE_URL": "https://tables.example.test"
                }),
            ) as load_dotenv,
        ):
            response = self.client.get(
                "/admin/tables",
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"https://tables.example.test/customer/menu?table=1",
            response.data,
        )
        load_dotenv.assert_called_once()

    def test_reachable_request_host_can_supply_the_qr_base_url(self):
        self.client.set_cookie(
            "admin_session",
            "test-session",
            domain="192.0.2.45",
        )
        with patch.dict(os.environ, {"CUSTOMER_QR_BASE_URL": ""}):
            response = self.client.get(
                "/admin/tables",
                base_url="https://192.0.2.45:5000",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"https://192.0.2.45:5000/customer/menu?table=6",
            response.data,
        )

    def test_invalid_or_local_base_urls_do_not_generate_qrs(self):
        invalid_urls = [
            "ftp://restaurant.example.test",
            "http://localhost:5000",
            "http://127.0.0.1:5000",
            "http://0.0.0.0:5000",
            "http://[::1]:5000",
            "http://user:password@192.168.1.24:5000",
            "http://192.0.2.24:abc",
            "http://bad host:5000",
            "https://restaurant.example.test/orders",
            "https://restaurant.example.test/?table=1",
        ]
        for base_url in invalid_urls:
            with self.subTest(base_url=base_url), patch.dict(
                os.environ,
                {"CUSTOMER_QR_BASE_URL": base_url},
            ):
                response = self.client.get(
                    "/admin/tables",
                    base_url="https://localhost",
                )

                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    b"Phone-ready QR codes are not configured",
                    response.data,
                )
                self.assertNotIn(b"data:image/png;base64,", response.data)

    def test_valid_https_url_is_normalized_and_used_for_each_table(self):
        with patch.dict(
            os.environ,
            {"CUSTOMER_QR_BASE_URL": "HTTPS://restaurant.example.test/"},
        ):
            response = self.client.get(
                "/admin/tables",
                base_url="https://localhost",
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            b"https://restaurant.example.test/customer/menu?table=1",
            response.data,
        )
        self.assertIn(
            b"https://restaurant.example.test/customer/menu?table=6",
            response.data,
        )

    def test_http_admin_request_does_not_advertise_https_qrs(self):
        with patch.dict(
            os.environ,
            {"CUSTOMER_QR_BASE_URL": "https://192.0.2.24:5000"},
        ):
            response = self.client.get(
                "/admin/tables",
                base_url="http://192.0.2.24:5000",
                environ_base={"REMOTE_ADDR": "192.0.2.45"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertNotIn(b"data:image/png;base64,", response.data)


if __name__ == "__main__":
    unittest.main()