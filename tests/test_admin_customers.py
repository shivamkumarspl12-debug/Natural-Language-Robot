import os
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

import app as app_module
from firebase_admin import auth as firebase_auth
from firebase_admin import exceptions as firebase_exceptions
from google.api_core.exceptions import GoogleAPICallError
from customer_orders import ORDER_COLLECTION, aggregate_customer_orders
from firestore_fakes import MemoryFirestore


class CustomerAggregationTests(unittest.TestCase):

    def test_aggregates_identified_and_unmatched_orders_without_duplicates(self):
        now = datetime(2025, 4, 10, 12, 0, tzinfo=timezone.utc)
        identity = "a" * 64
        linked_order = {
            "id": "QR-IDENTIFIED-1",
            "customer_identity": identity,
            "customer_name": "Older Name",
            "phone_last4": "0188",
            "created_at": "2025-04-08T09:00:00+00:00",
            "table_number": 2,
            "total": 10.25,
            "items": [{"name": "Garden Margherita", "quantity": 1}],
        }
        recent_linked_order = {
            **linked_order,
            "id": "QR-IDENTIFIED-2",
            "customer_name": "Current Name",
            "created_at": "2025-04-10T10:00:00+00:00",
            "total": 20.25,
        }
        unmatched_one = {
            "id": "QR-LEGACY-1",
            "customer_name": "Legacy Guest One",
            "phone_last4": "7777",
            "created_at": "2025-04-09T09:00:00+00:00",
            "total": 5,
            "items": [],
        }
        unmatched_two = {
            **unmatched_one,
            "id": "QR-LEGACY-2",
            "customer_name": "Legacy Guest Two",
            "created_at": "2025-04-09T10:00:00+00:00",
            "total": 7,
        }

        result = aggregate_customer_orders(
            [
                linked_order,
                recent_linked_order,
                recent_linked_order,
                unmatched_one,
                unmatched_two,
            ],
            now=now,
        )

        self.assertEqual(result["summary"]["total_customers"], 3)
        self.assertEqual(result["summary"]["total_orders"], 4)
        self.assertEqual(result["summary"]["returning_rate_percent"], 33)
        self.assertEqual(result["summary"]["average_order_spend"], 10.63)
        self.assertEqual(result["summary"]["new_customers_this_week"], 3)
        identified = next(
            customer for customer in result["customers"]
            if customer["identity_available"]
        )
        self.assertEqual(identified["id"], identity)
        self.assertEqual(identified["name"], "Current Name")
        self.assertEqual(identified["phone"], "•••• 0188")
        self.assertEqual(identified["order_count"], 2)
        self.assertEqual(identified["total_spending"], 30.5)
        self.assertEqual(
            identified["last_order_at"],
            "2025-04-10T10:00:00+00:00",
        )
        self.assertEqual(
            [order["id"] for order in identified["orders_history"]],
            ["QR-IDENTIFIED-2", "QR-IDENTIFIED-1"],
        )
        unmatched = [
            customer for customer in result["customers"]
            if not customer["identity_available"]
        ]
        self.assertEqual(len(unmatched), 2)
        self.assertTrue(all("Unmatched" in customer["phone"] for customer in unmatched))

    def test_normalized_phone_identity_is_stable_and_secret_is_required_for_matching(self):
        with patch.dict(os.environ, {"CUSTOMER_ID_HMAC_KEY": "k" * 64}):
            first = app_module.customer_identity_for_phone("5035550188")
            second = app_module.customer_identity_for_phone("5035550188")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 64)

        with patch.dict(os.environ, {"CUSTOMER_ID_HMAC_KEY": ""}):
            self.assertIsNone(
                app_module.customer_identity_for_phone("5035550188")
            )


class AdminCustomerApiTests(unittest.TestCase):

    def setUp(self):
        app_module.app.config["TESTING"] = True
        app_module.app.config["FIREBASE_ADMIN_UIDS"] = {"allowed-admin"}
        self.client = app_module.app.test_client()
        self.client.set_cookie("admin_session", "test-session")
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "customer_orders.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)
        self.session_verification = patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "allowed-admin"},
        )
        self.session_verification.start()
        self.addCleanup(self.session_verification.stop)

    def test_customers_page_uses_live_data_placeholders_not_fictional_rows(self):
        response = self.client.get("/admin/customers")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Loading Firestore customer data", response.data)
        self.assertIn(b"Firestore customer records", response.data)
        self.assertIn(b"FIRESTORE ORDERS", response.data)
        self.assertNotIn(b"Demo data", response.data)
        self.assertNotIn(b"Olivia Bennett", response.data)
        self.assertNotIn(b"1,284", response.data)

    def test_customer_api_derives_real_orders_masks_phone_and_returns_history(self):
        store = self.database.collections.setdefault(ORDER_COLLECTION, {})
        store["QR-ONE"] = {
            "id": "QR-ONE",
            "customer_identity": "b" * 64,
            "customer_name": "Jordan Guest",
            "phone_last4": "0188",
            "created_at": datetime(2025, 4, 9, 12, tzinfo=timezone.utc),
            "table_number": 3,
            "items": [{"name": "Garden Margherita", "quantity": 2}],
            "total": 37,
        }
        store["QR-TWO"] = {
            **store["QR-ONE"],
            "id": "QR-TWO",
            "created_at": datetime(2025, 4, 10, 12, tzinfo=timezone.utc),
            "total": 18.5,
        }

        response = self.client.get("/api/admin/customers")

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["summary"]["total_customers"], 1)
        self.assertEqual(body["summary"]["total_orders"], 2)
        self.assertEqual(body["customers"][0]["order_count"], 2)
        self.assertEqual(len(body["customers"][0]["orders_history"]), 2)
        self.assertEqual(body["customers"][0]["phone"], "•••• 0188")
        self.assertNotIn("5035550188", response.get_data(as_text=True))
        self.assertNotIn("customer_identity", response.get_data(as_text=True))

    def test_customer_api_returns_safe_error_when_firestore_is_unavailable(self):
        with patch(
            "customer_orders.get_firestore_client",
            side_effect=GoogleAPICallError("private transport details"),
        ):
            response = self.client.get("/api/admin/customers")

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "Customer data is temporarily unavailable.",
        )
        self.assertNotIn("private transport details", response.get_data(as_text=True))

    def test_customer_api_keeps_last_four_only_orders_separate(self):
        store = self.database.collections.setdefault(ORDER_COLLECTION, {})
        store["QR-LEGACY-ONE"] = {
            "id": "QR-LEGACY-ONE",
            "customer_name": "Legacy Guest One",
            "phone_last4": "0188",
            "total": 12,
            "items": [],
        }
        store["QR-LEGACY-TWO"] = {
            **store["QR-LEGACY-ONE"],
            "id": "QR-LEGACY-TWO",
            "customer_name": "Legacy Guest Two",
        }

        response = self.client.get("/api/admin/customers")

        self.assertEqual(response.status_code, 200)
        customers = response.get_json()["customers"]
        self.assertEqual(len(customers), 2)
        self.assertTrue(all(not customer["identity_available"] for customer in customers))
        self.assertTrue(all(customer["phone"] == "Unmatched · •••• 0188" for customer in customers))

    def test_admin_page_and_api_require_a_valid_session(self):
        self.client.delete_cookie("admin_session")

        page_response = self.client.get("/admin/customers")
        api_response = self.client.get("/api/admin/customers")
        dashboard_response = self.client.get("/admin")

        self.assertEqual(page_response.status_code, 302)
        self.assertIn("/admin-login", page_response.headers["Location"])
        self.assertEqual(api_response.status_code, 401)
        self.assertEqual(dashboard_response.status_code, 302)
        self.assertIn("/admin-login", dashboard_response.headers["Location"])
        self.assertIn("next=/admin", dashboard_response.headers["Location"])

    def test_admin_login_uses_only_safe_admin_next_paths(self):
        safe_path = self.client.get(
            "/admin-login?next=%2Fadmin%2Forders%3Fstatus%3Dnew"
        )
        external_path = self.client.get(
            "/admin-login?next=https%3A%2F%2Fevil.example"
        )
        protocol_relative_path = self.client.get(
            "/admin-login?next=%2F%2Fevil.example"
        )
        unrelated_path = self.client.get("/admin-login?next=%2F")

        self.assertEqual(safe_path.status_code, 200)
        self.assertIn(
            b'window.adminNextPath = "/admin/orders?status=new";',
            safe_path.data,
        )
        for response in (external_path, protocol_relative_path, unrelated_path):
            with self.subTest(response=response):
                self.assertEqual(response.status_code, 200)
                self.assertIn(
                    b'window.adminNextPath = "/admin";',
                    response.data,
                )

    def test_dashboard_launch_cards_use_existing_flask_route_endpoints(self):
        response = self.client.get("/admin")

        self.assertEqual(response.status_code, 200)
        for label, endpoint in (
            ("Open Main Website", "home"),
            ("Open 3D Simulation", "simulation"),
            ("Open Voice + Camera", "voice_camera"),
        ):
            with self.subTest(label=label):
                route = next(
                    rule.rule
                    for rule in app_module.app.url_map.iter_rules()
                    if rule.endpoint == endpoint
                )
                self.assertIn(label.encode(), response.data)
                self.assertIn(
                    f'href="{route}"'.encode(),
                    response.data,
                )

    def test_linked_pages_open_and_customer_routes_remain_public(self):
        for path in ("/", "/simulation", "/voice-camera"):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

        for path in (
            "/customer/menu?table=1",
            "/customer/cart?table=1",
            "/customer/checkout?table=1",
            "/customer/order-status?table=1",
        ):
            with self.subTest(path=path):
                response = self.client.get(path)
                self.assertEqual(response.status_code, 200)

    def test_session_creation_verifies_firebase_token_and_sets_http_only_cookie(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                return_value={"uid": "allowed-admin"},
            ) as verify_token,
            patch(
                "app.firebase_auth.create_session_cookie",
                return_value="signed-session-cookie",
            ) as create_cookie,
        ):
            response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn("HttpOnly", response.headers["Set-Cookie"])
        self.assertIn("admin_session=signed-session-cookie", response.headers["Set-Cookie"])
        verify_token.assert_called_once()
        self.assertEqual(
            verify_token.call_args.kwargs["clock_skew_seconds"],
            30,
        )
        create_cookie.assert_called_once()

    def test_created_session_cookie_authorizes_dashboard_request(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                return_value={"uid": "allowed-admin"},
            ),
            patch(
                "app.firebase_auth.create_session_cookie",
                return_value="signed-session-cookie",
            ),
            patch(
                "app.firebase_auth.verify_session_cookie",
                return_value={"uid": "allowed-admin"},
            ) as verify_session,
        ):
            login_response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )
            dashboard_response = self.client.get("/admin")

        self.assertEqual(login_response.status_code, 200)
        self.assertIn(
            "admin_session=signed-session-cookie",
            login_response.headers["Set-Cookie"],
        )
        self.assertEqual(dashboard_response.status_code, 200)
        self.assertIn(b"Restaurant overview", dashboard_response.data)
        verify_session.assert_called_once()
        self.assertEqual(
            verify_session.call_args.args[0],
            "signed-session-cookie",
        )
        self.assertTrue(verify_session.call_args.kwargs["check_revoked"])
        self.assertEqual(
            verify_session.call_args.kwargs["clock_skew_seconds"],
            30,
        )

    def test_session_creation_reports_expired_id_token(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                side_effect=firebase_auth.ExpiredIdTokenError(
                    "private token details",
                    cause=None,
                ),
            ),
        ):
            response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn("token expired", response.get_json()["error"])
        self.assertNotIn("private token details", response.get_data(as_text=True))

    def test_session_creation_reports_revoked_id_token(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                side_effect=firebase_auth.RevokedIdTokenError(
                    "private token details",
                ),
            ),
        ):
            response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn("session was revoked", response.get_json()["error"])
        self.assertNotIn("private token details", response.get_data(as_text=True))

    def test_session_creation_gives_safe_guidance_for_invalid_id_token(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                side_effect=firebase_auth.InvalidIdTokenError("private token details"),
            ),
        ):
            response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )

        self.assertEqual(response.status_code, 401)
        self.assertIn(
            "computer's clock",
            response.get_json()["error"],
        )
        self.assertNotIn(
            "private token details",
            response.get_data(as_text=True),
        )

    def test_session_creation_reports_firebase_certificate_network_failure(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                side_effect=firebase_auth.CertificateFetchError(
                    "certificate fetch failed",
                    RuntimeError("private network details"),
                ),
            ),
        ):
            response = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn(
            "server internet connection",
            response.get_json()["error"],
        )
        self.assertNotIn(
            "private network details",
            response.get_data(as_text=True),
        )

    def test_session_creation_rejects_non_admin_and_cross_origin_requests(self):
        with (
            patch("app.get_firebase_app", return_value=object()),
            patch(
                "app.firebase_auth.verify_id_token",
                return_value={"uid": "ordinary-user"},
            ),
            patch("app.firebase_auth.create_session_cookie") as create_cookie,
        ):
            forbidden = self.client.post(
                "/api/admin/session",
                json={"idToken": "t" * 120},
                headers={"Origin": "http://localhost"},
            )
        cross_origin = self.client.post(
            "/api/admin/session",
            json={"idToken": "t" * 120},
            headers={"Origin": "https://attacker.example"},
        )

        self.assertEqual(forbidden.status_code, 403)
        self.assertEqual(cross_origin.status_code, 403)
        create_cookie.assert_not_called()

    def test_session_cookie_for_non_admin_is_rejected(self):
        with patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "ordinary-user"},
        ):
            response = self.client.get("/api/admin/customers")

        self.assertEqual(response.status_code, 403)

    def test_insecure_remote_admin_access_is_rejected(self):
        response = self.client.get(
            "/admin-login",
            base_url="http://192.0.2.10:5000",
        )

        self.assertEqual(response.status_code, 403)
        self.assertIn(b"requires HTTPS", response.data)

    def test_robot_tracking_api_keeps_its_route_but_requires_admin_session(self):
        self.client.delete_cookie("admin_session")
        unauthorized = self.client.get("/api/robot-tracking")
        self.client.set_cookie("admin_session", "test-session")
        authorized = self.client.get("/api/robot-tracking")

        self.assertEqual(unauthorized.status_code, 401)
        self.assertEqual(authorized.status_code, 200)
        self.assertIn("tables", authorized.get_json())


if __name__ == "__main__":
    unittest.main()
