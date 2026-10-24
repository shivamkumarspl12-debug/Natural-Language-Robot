import importlib
import os
import tempfile
import unittest
import uuid
from datetime import timezone
from pathlib import Path
from unittest.mock import patch

from google.api_core.exceptions import GoogleAPICallError
from werkzeug.middleware.proxy_fix import ProxyFix
from firebase_admin import exceptions as firebase_exceptions

import app as app_module
from customer_orders import ORDER_COLLECTION, save_customer_order
import firebase_db
from firebase_db import FirebaseConfigurationError
from firestore_fakes import MemoryFirestore


class FirestoreCustomerOrderTests(unittest.TestCase):

    def setUp(self):
        app_module.app.config["TESTING"] = True
        app_module.app.config["FIREBASE_ADMIN_UIDS"] = {"test-admin"}
        self.client = app_module.app.test_client()
        self.client.set_cookie("admin_session", "test-session")
        self.auth_patch = patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "test-admin"},
        )
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.identity_key_patch = patch.dict(
            os.environ,
            {"CUSTOMER_ID_HMAC_KEY": "test-customer-identity-key-" * 3},
        )
        self.identity_key_patch.start()
        self.addCleanup(self.identity_key_patch.stop)
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "customer_orders.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)
        self.transaction_patch = patch(
            "customer_orders.firestore.transactional",
            side_effect=lambda function: lambda transaction: function(transaction),
        )
        self.transaction_patch.start()
        self.addCleanup(self.transaction_patch.stop)
        seeded_menu = self.client.get("/api/admin/menu")
        self.assertEqual(seeded_menu.status_code, 200)

    def valid_order_payload(self):
        return {
            "customer_name": "Jordan Guest",
            "customer_phone": "5035550188",
            "table_number": 6,
            "items": [{"id": "garden-margherita", "quantity": 2}],
        }

    def post_order(self, payload, headers=None):
        request_headers = {
            "Origin": "http://localhost",
            "X-Order-Access-Token": "T" * 43,
        }
        request_headers.update(headers or {})
        return self.client.post(
            "/api/customer/orders",
            json=payload,
            headers=request_headers,
        )

    def create_authorized_order(self, token="T" * 43):
        response = self.client.post(
            "/api/customer/orders",
            json=self.valid_order_payload(),
            headers={
                "Origin": "http://localhost",
                "X-Order-Access-Token": token,
            },
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["order"]

    def advance_order_to_ready(self, order):
        for revision, status in enumerate(
            ("Accepted", "Preparing", "Ready"),
            start=0,
        ):
            response = self.client.put(
                f"/api/admin/orders/{order['id']}",
                json={"status": status, "revision": revision},
            )
            self.assertEqual(response.status_code, 200)
        return response.get_json()["order"]

    def test_simulation_queue_requires_admin_and_claims_ready_orders_once(self):
        first = self.create_authorized_order("A" * 43)
        second = self.create_authorized_order("B" * 43)
        waiting = self.create_authorized_order("W" * 43)
        self.advance_order_to_ready(first)
        second = self.advance_order_to_ready(second)

        unauthenticated = app_module.app.test_client().get(
            "/api/admin/simulation/orders",
        )
        self.assertEqual(unauthenticated.status_code, 401)

        queued = self.client.get("/api/admin/simulation/orders")
        self.assertEqual(queued.status_code, 200)
        self.assertEqual(
            {order["id"] for order in queued.get_json()["orders"]},
            {first["id"], second["id"]},
        )
        self.assertNotIn(
            waiting["id"],
            {order["id"] for order in queued.get_json()["orders"]},
        )
        self.assertEqual(
            queued.get_json()["pending_orders"][0]["id"],
            waiting["id"],
        )
        self.assertEqual(
            queued.get_json()["pending_orders"][0]["status"],
            "Order Placed",
        )
        selected = next(
            order
            for order in queued.get_json()["orders"]
            if order["id"] == second["id"]
        )
        mission_id = str(uuid.uuid4())
        claimed = self.client.post(
            f"/api/admin/simulation/orders/{second['id']}/claim",
            json={"mission_id": mission_id, "revision": selected["revision"]},
        )
        self.assertEqual(claimed.status_code, 200)
        self.assertEqual(claimed.get_json()["order"]["status"], "Robot Delivery")
        self.assertEqual(claimed.get_json()["order"]["table_number"], 6)
        self.assertEqual(claimed.get_json()["order"]["items"][0]["name"], "Garden Margherita")

        remaining = self.client.get("/api/admin/simulation/orders")
        self.assertEqual(
            [order["id"] for order in remaining.get_json()["orders"]],
            [first["id"]],
        )
        duplicate_claim = self.client.post(
            f"/api/admin/simulation/orders/{second['id']}/claim",
            json={"mission_id": mission_id, "revision": selected["revision"]},
        )
        self.assertEqual(duplicate_claim.status_code, 200)
        self.assertEqual(
            duplicate_claim.get_json()["order"]["delivery_simulation_id"],
            mission_id,
        )

    def test_accepted_customer_order_is_visible_but_not_mission_eligible(self):
        access_token = "Q" * 43
        order = self.create_authorized_order(access_token)
        accepted = self.client.put(
            f"/api/admin/orders/{order['id']}",
            json={"status": "Accepted", "revision": 0},
        )
        self.assertEqual(accepted.status_code, 200)
        self.assertEqual(accepted.get_json()["order"]["status"], "Accepted")

        customer_status = self.client.get(
            f"/api/customer/orders/{order['id']}",
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(
            customer_status.get_json()["order"]["status"],
            "Accepted",
        )
        simulation = self.client.get("/api/admin/simulation/orders")
        self.assertEqual(simulation.status_code, 200)
        payload = simulation.get_json()
        self.assertEqual(payload["orders"], [])
        self.assertEqual(len(payload["pending_orders"]), 1)
        visible = payload["pending_orders"][0]
        self.assertEqual(visible["id"], order["id"])
        self.assertEqual(visible["customer_name"], "Jordan Guest")
        self.assertEqual(visible["table_number"], 6)
        self.assertEqual(
            visible["items"],
            [{"id": "garden-margherita", "name": "Garden Margherita", "price": 18.5, "quantity": 2}],
        )
        self.assertEqual(visible["total"], 37.0)
        self.assertEqual(visible["status"], "Accepted")
        self.assertTrue(visible["created_at"])
        self.assertFalse(visible["delivery_eligible"])
        simulation_page = self.client.get("/simulation")
        self.assertEqual(simulation_page.status_code, 200)
        self.assertIn(b"Loading current orders from Firestore", simulation_page.data)
        self.assertIn(b"mission-created", simulation_page.data)

        mission_id = str(uuid.uuid4())
        not_ready = self.client.post(
            f"/api/admin/simulation/orders/{order['id']}/claim",
            json={"mission_id": mission_id, "revision": visible["revision"]},
        )
        self.assertEqual(not_ready.status_code, 409)
        self.assertEqual(
            self.database.collections[ORDER_COLLECTION][order["id"]]["status"],
            "Accepted",
        )
        self.assertEqual(
            self.client.get("/api/admin/simulation/orders").get_json()["pending_orders"][0]["id"],
            order["id"],
        )

    def test_customer_tracking_shows_only_authorized_order_simulation_position(self):
        access_token = "T" * 43
        ready = self.advance_order_to_ready(
            self.create_authorized_order(access_token)
        )
        tracking_url = f"/api/customer/orders/{ready['id']}/tracking"
        ready_tracking = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(ready_tracking.status_code, 200)
        self.assertIsNone(ready_tracking.get_json()["tracking"]["position"])
        self.assertIn(
            "has not started yet",
            ready_tracking.get_json()["tracking"]["message"],
        )
        mission_id = str(uuid.uuid4())
        claim = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/claim",
            json={"mission_id": mission_id, "revision": ready["revision"]},
        )
        self.assertEqual(claim.status_code, 200)

        wrong_token = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": "X" * 43},
        )
        missing_token = self.client.get(tracking_url)
        self.assertEqual(wrong_token.status_code, 404)
        self.assertEqual(missing_token.status_code, 404)

        before_position = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(before_position.status_code, 200)
        self.assertEqual(
            before_position.get_json()["tracking"]["status"],
            "Robot Delivery",
        )
        self.assertFalse(before_position.get_json()["tracking"]["position"]["moving"])

        unauthenticated_admin = app_module.app.test_client().post(
            f"/api/admin/simulation/orders/{ready['id']}/position",
            json={
                "mission_id": mission_id,
                "x": 2.5,
                "z": -3.0,
                "moving": True,
            },
        )
        self.assertEqual(unauthenticated_admin.status_code, 401)

        position_update = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/position",
            json={
                "mission_id": mission_id,
                "x": 2.5,
                "z": -3.0,
                "moving": True,
            },
        )
        self.assertEqual(position_update.status_code, 200)
        customer_tracking = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(customer_tracking.status_code, 200)
        self.assertEqual(
            customer_tracking.headers["Cache-Control"],
            "private, no-store, max-age=0",
        )
        payload = customer_tracking.get_json()["tracking"]
        self.assertEqual(payload["position"]["x"], 2.5)
        self.assertEqual(payload["position"]["z"], -3.0)
        self.assertTrue(payload["position"]["moving"])
        self.assertEqual(payload["destination_table"], ready["table_number"])
        self.assertEqual(
            set(payload),
            {
                "order_id",
                "status",
                "destination_table",
                "position",
                "simulated",
                "message",
            },
        )
        self.assertNotIn("customer_name", payload)
        self.assertNotIn("items", payload)
        self.assertNotIn("retry_count", payload)
        self.assertNotIn("battery", payload)

        lan_http_tracking = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": access_token},
            base_url="http://192.0.2.10:5000",
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )
        self.assertEqual(lan_http_tracking.status_code, 403)
        self.assertEqual(lan_http_tracking.content_type, "application/json")
        self.assertIn("requires HTTPS", lan_http_tracking.get_json()["error"])
        lan_https_tracking = self.client.get(
            tracking_url,
            headers={"X-Order-Access-Token": access_token},
            base_url="https://192.0.2.10:5000",
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )
        self.assertEqual(lan_https_tracking.status_code, 200)

        invalid_mission = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/position",
            json={
                "mission_id": str(uuid.uuid4()),
                "x": 5,
                "z": 4,
                "moving": False,
            },
        )
        self.assertEqual(invalid_mission.status_code, 404)

    def test_customer_order_apis_reject_lan_http_before_receiving_access_tokens(self):
        response = self.client.post(
            "/api/customer/orders",
            json=self.valid_order_payload(),
            headers={"X-Order-Access-Token": "H" * 43},
            base_url="http://192.0.2.10:5000",
            environ_base={"REMOTE_ADDR": "192.0.2.20"},
        )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.content_type, "application/json")
        self.assertIn("requires HTTPS", response.get_json()["error"])
        self.assertFalse(self.database.collections.get(ORDER_COLLECTION))

    def test_simulation_status_matching_normalizes_case_and_whitespace(self):
        order = self.create_authorized_order()
        stored = self.database.collections[ORDER_COLLECTION][order["id"]]
        stored["status"] = "  aCcEpTeD  "

        response = self.client.get("/api/admin/simulation/orders")

        self.assertEqual(response.status_code, 200)
        pending = response.get_json()["pending_orders"]
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["status"], "Accepted")
        self.assertEqual(stored["status"], "  aCcEpTeD  ")

    def test_lan_simulation_api_requires_https_and_admin_authentication(self):
        order = self.create_authorized_order()
        self.client.put(
            f"/api/admin/orders/{order['id']}",
            json={"status": "Accepted", "revision": 0},
        )
        simulation = app_module.app.test_client()
        public_page = simulation.get(
            "/simulation",
            base_url="http://192.0.2.10:5000",
        )
        self.assertEqual(public_page.status_code, 403)
        self.assertIn(b"requires HTTPS", public_page.data)

        secure_unauthorized_page = simulation.get(
            "/simulation",
            base_url="https://192.0.2.10:5000",
        )
        self.assertEqual(secure_unauthorized_page.status_code, 302)
        self.assertIn("/admin-login", secure_unauthorized_page.headers["Location"])

        insecure_api = simulation.get(
            "/api/admin/simulation/orders",
            base_url="http://192.0.2.10:5000",
        )
        self.assertEqual(insecure_api.status_code, 403)
        self.assertIn("requires HTTPS", insecure_api.get_json()["error"])
        self.assertEqual(
            insecure_api.headers["Cache-Control"],
            "private, no-store, max-age=0",
        )

        secure_unauthorized = simulation.get(
            "/api/admin/simulation/orders",
            base_url="https://192.0.2.10:5000",
        )
        self.assertEqual(secure_unauthorized.status_code, 401)

        simulation.set_cookie(
            "admin_session",
            "test-session",
            domain="192.0.2.10",
        )
        secure_authorized = simulation.get(
            "/api/admin/simulation/orders",
            base_url="https://192.0.2.10:5000",
        )
        self.assertEqual(secure_authorized.status_code, 200)
        self.assertEqual(
            secure_authorized.headers["Cache-Control"],
            "private, no-store, max-age=0",
        )
        self.assertEqual(
            secure_authorized.get_json()["pending_orders"][0]["id"],
            order["id"],
        )
        original_wsgi_app = app_module.app.wsgi_app
        try:
            app_module.app.wsgi_app = ProxyFix(original_wsgi_app, x_proto=1)
            proxied_client = app_module.app.test_client()
            proxied_client.set_cookie(
                "admin_session",
                "test-session",
                domain="192.0.2.10",
            )
            proxied_response = proxied_client.get(
                "/api/admin/simulation/orders",
                base_url="http://192.0.2.10:5000",
                headers={"X-Forwarded-Proto": "https"},
            )
        finally:
            app_module.app.wsgi_app = original_wsgi_app
        self.assertEqual(proxied_response.status_code, 200)
        self.assertEqual(
            proxied_response.get_json()["pending_orders"][0]["id"],
            order["id"],
        )

    def test_failed_simulation_is_idempotent_and_cannot_be_completed(self):
        ready = self.advance_order_to_ready(
            self.create_authorized_order("F" * 43)
        )
        mission_id = str(uuid.uuid4())
        claimed = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/claim",
            json={"mission_id": mission_id, "revision": ready["revision"]},
        )
        self.assertEqual(claimed.status_code, 200)

        fail_url = f"/api/admin/simulation/orders/{ready['id']}/fail"
        failed = self.client.post(fail_url, json={"mission_id": mission_id})
        self.assertEqual(failed.status_code, 200)
        self.assertEqual(failed.get_json()["order"]["status"], "Failed")
        repeated = self.client.post(fail_url, json={"mission_id": mission_id})
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.get_json()["order"]["status"], "Failed")
        completed = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/complete",
            json={"mission_id": mission_id},
        )
        self.assertEqual(completed.status_code, 409)

    def test_simulation_completion_is_idempotent_and_synced_to_customer_and_admin(self):
        access_token = "D" * 43
        ready = self.advance_order_to_ready(
            self.create_authorized_order(access_token)
        )
        mission_id = str(uuid.uuid4())
        claim = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/claim",
            json={"mission_id": mission_id, "revision": ready["revision"]},
        )
        self.assertEqual(claim.status_code, 200)

        completed = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/complete",
            json={"mission_id": mission_id},
        )
        self.assertEqual(completed.status_code, 200)
        self.assertEqual(completed.get_json()["order"]["status"], "Delivered")
        repeated = self.client.post(
            f"/api/admin/simulation/orders/{ready['id']}/complete",
            json={"mission_id": mission_id},
        )
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.get_json()["order"]["status"], "Delivered")

        customer_status = self.client.get(
            f"/api/customer/orders/{ready['id']}",
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(customer_status.status_code, 200)
        self.assertEqual(customer_status.get_json()["order"]["status"], "Delivered")
        queue_after_delivery = self.client.get("/api/admin/simulation/orders")
        self.assertEqual(queue_after_delivery.get_json()["orders"], [])
        self.assertEqual(queue_after_delivery.get_json()["pending_orders"], [])
        tracking = self.client.get("/api/robot-tracking")
        self.assertEqual(tracking.status_code, 200)
        tracking_data = tracking.get_json()
        self.assertEqual(tracking_data["current_order_id"], ready["id"])
        self.assertEqual(tracking_data["destination_table"], ready["table_number"])
        self.assertEqual(tracking_data["delivery_status"], "Delivered")
        self.assertIn("not a physical robot", tracking_data["source"])
        admin_page = self.client.get("/admin/orders")
        self.assertEqual(admin_page.status_code, 200)
        self.assertIn(b"Delivered", admin_page.data)

        invalid_admin_transition = self.client.put(
            f"/api/admin/orders/{ready['id']}",
            json={"status": "Cancelled", "revision": completed.get_json()["order"]["revision"]},
        )
        self.assertEqual(invalid_admin_transition.status_code, 409)

    def test_cancelled_orders_cannot_be_claimed_and_production_blocks_simulation(self):
        cancelled = self.create_authorized_order("C" * 43)
        self.client.delete(
            f"/api/customer/orders/{cancelled['id']}",
            json={"revision": 0},
            headers={"X-Order-Access-Token": "C" * 43},
        )
        cancelled_claim = self.client.post(
            f"/api/admin/simulation/orders/{cancelled['id']}/claim",
            json={"mission_id": str(uuid.uuid4()), "revision": 1},
        )
        self.assertEqual(cancelled_claim.status_code, 409)
        cancelled_queue = self.client.get("/api/admin/simulation/orders")
        self.assertNotIn(
            cancelled["id"],
            {
                order["id"]
                for order in (
                    cancelled_queue.get_json()["orders"]
                    + cancelled_queue.get_json()["pending_orders"]
                )
            },
        )

        ready = self.advance_order_to_ready(
            self.create_authorized_order("E" * 43)
        )
        with patch.dict(os.environ, {"APP_ENV": "production"}):
            production_claim = self.client.post(
                f"/api/admin/simulation/orders/{ready['id']}/claim",
                json={
                    "mission_id": str(uuid.uuid4()),
                    "revision": ready["revision"],
                },
            )
        self.assertEqual(production_claim.status_code, 403)
        self.assertEqual(
            self.database.collections[ORDER_COLLECTION][ready["id"]]["status"],
            "Ready",
        )

    def test_order_is_stored_and_available_after_app_reload(self):
        response = self.post_order(
            self.valid_order_payload(),
            {"Idempotency-Key": "checkout-attempt-1"},
        )

        self.assertEqual(response.status_code, 201)
        order = response.get_json()["order"]
        self.assertTrue(order["id"].startswith("QR-"))
        self.assertEqual(order["created_at"][-6:], "+00:00")
        self.assertEqual(order["status"], "Order Placed")
        self.assertEqual(order["table_number"], 6)
        self.assertEqual(
            order["items"],
            [{
                "id": "garden-margherita",
                "name": "Garden Margherita",
                "price": 18.5,
                "quantity": 2,
            }],
        )
        self.assertEqual(order["total"], 37.0)
        self.assertEqual(len(self.database.collections[ORDER_COLLECTION]), 1)
        stored_order = next(
            iter(self.database.collections[ORDER_COLLECTION].values())
        )
        self.assertEqual(len(stored_order["customer_identity"]), 64)
        self.assertNotIn("customer_identity", order)

        previous_flask_app = app_module.app
        restarted_module = importlib.reload(app_module)
        restarted_module.app.config["TESTING"] = True
        self.assertIsNot(restarted_module.app, previous_flask_app)
        restarted_client = restarted_module.app.test_client()
        status = restarted_client.get(
            f"/api/customer/orders/{order['id']}",
            headers={"X-Order-Access-Token": "T" * 43},
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["order"], order)

    def test_admin_orders_reads_persisted_firestore_order(self):
        created = self.post_order(self.valid_order_payload())
        self.assertEqual(created.status_code, 201)

        response = self.client.get("/admin/orders")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Jordan Guest", response.data)
        self.assertIn(b"Firestore", response.data)

    def test_idempotent_retry_returns_the_existing_order(self):
        payload = self.valid_order_payload()
        headers = {"Idempotency-Key": "retry-safe-key"}

        first = self.post_order(payload, headers)
        retry = self.post_order(payload, headers)

        self.assertEqual(first.status_code, 201)
        self.assertEqual(retry.status_code, 201)
        self.assertEqual(
            retry.get_json()["order"]["id"],
            first.get_json()["order"]["id"],
        )
        self.assertEqual(len(self.database.collections[ORDER_COLLECTION]), 1)

    def test_customer_order_creation_requires_private_access_token(self):
        response = self.client.post(
            "/api/customer/orders",
            json=self.valid_order_payload(),
            headers={
                "Origin": "http://localhost",
                "Idempotency-Key": "private-token-check-001",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("order access token is required", response.get_json()["error"])
        self.assertFalse(self.database.collections.get(ORDER_COLLECTION))

    def test_reusing_idempotency_key_for_different_order_returns_conflict(self):
        headers = {"Idempotency-Key": "same-key"}
        self.post_order(self.valid_order_payload(), headers)
        changed_payload = self.valid_order_payload()
        changed_payload["table_number"] = 5

        response = self.post_order(changed_payload, headers)

        self.assertEqual(response.status_code, 409)

    def test_invalid_order_id_is_not_found(self):
        response = self.client.get("/api/customer/orders/not-an-order")

        self.assertEqual(response.status_code, 404)

    def test_order_reads_and_edits_require_the_per_order_access_token(self):
        access_token = "S" * 43
        order = self.create_authorized_order(access_token)
        order_url = f"/api/customer/orders/{order['id']}"
        update = {
            "revision": 0,
            "items": [{"id": "garden-margherita", "quantity": 3}],
        }

        self.assertEqual(self.client.get(order_url).status_code, 404)
        unauthorized = self.client.put(
            order_url,
            json=update,
            headers={"X-Order-Access-Token": "X" * 43},
        )
        self.assertEqual(unauthorized.status_code, 404)

        edited = self.client.put(
            order_url,
            json=update,
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(edited.status_code, 200)
        edited_order = edited.get_json()["order"]
        self.assertEqual(edited_order["total"], 55.5)
        self.assertEqual(edited_order["items"][0]["quantity"], 3)
        self.assertEqual(edited_order["revision"], 1)
        self.assertNotIn("order_access_token_hash", edited_order)

        stale_edit = self.client.put(
            order_url,
            json=update,
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(stale_edit.status_code, 409)
        self.assertEqual(
            self.database.collections[ORDER_COLLECTION][order["id"]]["total"],
            55.5,
        )
        dashboard = self.client.get("/admin/orders")
        self.assertIn(order["id"].encode(), dashboard.data)
        self.assertIn(b"$55.50", dashboard.data)
        self.assertIn(b"3 \xc3\x97 Garden Margherita", dashboard.data)

    def test_cancel_allowed_states_and_admin_status_updates_persist(self):
        access_token = "C" * 43
        order = self.create_authorized_order(access_token)
        order_url = f"/api/customer/orders/{order['id']}"

        cancelled = self.client.delete(
            order_url,
            json={"revision": 0},
            headers={"X-Order-Access-Token": access_token},
        )
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.get_json()["order"]["status"], "Cancelled")

        next_order = self.create_authorized_order("R" * 43)
        admin_url = f"/api/admin/orders/{next_order['id']}"
        unauthorized = app_module.app.test_client().put(
            admin_url,
            json={"status": "Preparing", "revision": 0},
        )
        self.assertEqual(unauthorized.status_code, 401)

        out_of_order = self.client.put(
            admin_url,
            json={"status": "Preparing", "revision": 0},
        )
        self.assertEqual(out_of_order.status_code, 409)
        updated = self.client.put(
            admin_url,
            json={"status": "Accepted", "revision": 0},
        )
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(updated.get_json()["order"]["status"], "Accepted")
        self.assertEqual(updated.get_json()["order"]["revision"], 1)
        status = self.client.get(
            f"/api/customer/orders/{next_order['id']}",
            headers={"X-Order-Access-Token": "R" * 43},
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.get_json()["order"]["status"], "Accepted")

        too_late = self.client.delete(
            f"/api/customer/orders/{next_order['id']}",
            json={"revision": 1},
            headers={"X-Order-Access-Token": "R" * 43},
        )
        self.assertEqual(too_late.status_code, 200)
        self.assertEqual(too_late.get_json()["order"]["status"], "Cancelled")

        preparing_order = self.create_authorized_order("P" * 43)
        preparing_url = f"/api/admin/orders/{preparing_order['id']}"
        accepted = self.client.put(
            preparing_url,
            json={"status": "Accepted", "revision": 0},
        )
        self.assertEqual(accepted.status_code, 200)
        preparing = self.client.put(
            preparing_url,
            json={"status": "Preparing", "revision": 1},
        )
        self.assertEqual(preparing.status_code, 200)
        cannot_cancel = self.client.delete(
            f"/api/customer/orders/{preparing_order['id']}",
            json={"revision": 2},
            headers={"X-Order-Access-Token": "P" * 43},
        )
        self.assertEqual(cannot_cancel.status_code, 409)

        dashboard = self.client.get("/admin/orders")
        self.assertIn(preparing_order["id"].encode(), dashboard.data)
        self.assertIn(b"Preparing", dashboard.data)

    def test_missing_firebase_configuration_returns_actionable_error(self):
        with patch(
            "customer_orders.get_firestore_client",
            side_effect=FirebaseConfigurationError(
                "Set FIREBASE_CREDENTIALS_PATH to a valid service-account file."
            ),
        ):
            response = self.client.post(
                "/api/customer/orders",
                json=self.valid_order_payload(),
                headers={
                    "Origin": "http://localhost",
                    "X-Order-Access-Token": "T" * 43,
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn(
            "FIREBASE_CREDENTIALS_PATH",
            response.get_json()["error"],
        )

    def test_firestore_write_error_returns_safe_service_error(self):
        with patch(
            "customer_orders.get_firestore_client",
            side_effect=GoogleAPICallError("private transport details"),
        ):
            response = self.client.post(
                "/api/customer/orders",
                json=self.valid_order_payload(),
                headers={
                    "Origin": "http://localhost",
                    "X-Order-Access-Token": "T" * 43,
                },
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "Order storage is temporarily unavailable. Please try again.",
        )
        self.assertNotIn(b"private transport details", response.data)

    def test_firebase_write_error_returns_safe_service_error(self):
        with patch(
            "app.save_customer_order",
            side_effect=firebase_exceptions.FirebaseError(
                "internal",
                "private firebase details"
            ),
        ):
            response = self.post_order(self.valid_order_payload())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "Order storage is temporarily unavailable. Please try again.",
        )
        self.assertNotIn(b"private firebase details", response.data)

    def test_firestore_status_read_error_returns_safe_service_error(self):
        order_id = f"QR-{'A' * 32}"
        with patch(
            "customer_orders.get_firestore_client",
            side_effect=GoogleAPICallError("private transport details"),
        ):
            response = self.client.get(
                f"/api/customer/orders/{order_id}",
                headers={"X-Order-Access-Token": "T" * 43},
            )

        self.assertEqual(response.status_code, 503)
        self.assertEqual(
            response.get_json()["error"],
            "Order storage is temporarily unavailable. Please try again.",
        )
        self.assertNotIn(b"private transport details", response.data)

    def test_repository_stores_server_timestamp_not_client_timestamp(self):
        order = {
            "customer_name": "Jordan Guest",
            "phone_last4": "0188",
            "table_number": 6,
            "items": [{"id": "garden-margherita", "quantity": 2}],
            "total": 37.0,
            "status": "Received by Flask demo",
            "demo_only": True,
        }

        stored = save_customer_order(order)
        raw_record = self.database.collections[ORDER_COLLECTION][stored["id"]]

        self.assertEqual(raw_record["created_at"].tzinfo, timezone.utc)
        self.assertEqual(stored["total"], 37.0)

    def test_firebase_admin_client_is_initialized_once(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            credential_path = Path(temporary_directory) / "service-account.json"
            credential_path.touch()
            with (
                patch.dict(
                    os.environ,
                    {"FIREBASE_CREDENTIALS_PATH": str(credential_path)},
                ),
                patch.object(firebase_db, "_firestore_client", None),
                patch.object(firebase_db, "_firebase_app", None),
                patch.object(
                    firebase_db.firebase_admin,
                    "get_app",
                    side_effect=ValueError("not initialized"),
                ),
                patch.object(
                    firebase_db.firebase_admin,
                    "initialize_app",
                    return_value=object(),
                ) as initialize_app,
                patch.object(
                    firebase_db.credentials,
                    "Certificate",
                    return_value=object(),
                ),
                patch.object(
                    firebase_db.firestore,
                    "client",
                    return_value=object(),
                ) as firestore_client,
            ):
                first_client = firebase_db.get_firestore_client()
                second_client = firebase_db.get_firestore_client()

        self.assertIs(first_client, second_client)
        initialize_app.assert_called_once()
        firestore_client.assert_called_once()


if __name__ == "__main__":
    unittest.main()
