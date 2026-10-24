import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from google.api_core.exceptions import GoogleAPICallError

import analytics
import app as app_module
from customer_orders import ORDER_COLLECTION
from firestore_fakes import MemoryFirestore


class OrderAnalyticsTests(unittest.TestCase):

    def setUp(self):
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "analytics.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)
        self.now = datetime(2026, 10, 22, 18, 30, tzinfo=timezone.utc)
        self.timezone = ZoneInfo("America/Los_Angeles")

    def _order(self, order_id, created_at, **values):
        return {
            "id": order_id,
            "created_at": created_at,
            "status": "Order Placed",
            "total": 10,
            "items": [{"name": "Garden Margherita", "quantity": 1}],
            **values,
        }

    def test_empty_firestore_returns_zero_metrics_and_no_fabricated_averages(self):
        result = analytics.aggregate_order_analytics(
            [],
            0,
            self.now,
            "America/Los_Angeles",
            "",
        )

        self.assertEqual(result["total_orders"], 0)
        self.assertEqual(result["orders_today"], 0)
        self.assertEqual(result["orders_this_week"], 0)
        self.assertEqual(result["order_value_this_week"], 0)
        self.assertEqual(len(result["daily"]), 7)
        self.assertEqual(result["popular_dishes"], [])
        self.assertIsNone(result["average_delivery_minutes"])
        self.assertIsNone(result["robot_completion"])
        self.assertIsNone(result["currency"])

    def test_count_aggregation_supports_firestore_nested_and_flat_results(self):
        aggregation = type("Aggregation", (), {"value": 7})()

        self.assertEqual(
            analytics._aggregation_count_value([[aggregation]]),
            7,
        )
        self.assertEqual(
            analytics._aggregation_count_value([aggregation]),
            7,
        )
        self.assertEqual(analytics._aggregation_count_value([]), 0)

    def test_invalid_count_aggregation_raises_explicit_data_error(self):
        with self.assertRaises(analytics.AnalyticsDataError):
            analytics._aggregation_count_value([[]])
        with self.assertRaises(analytics.AnalyticsDataError):
            analytics._aggregation_count_value([[object()]])

    def test_firestore_query_uses_local_week_and_counts_unique_orders(self):
        local_midnight = datetime(2026, 10, 19, 0, tzinfo=self.timezone)
        before_week = local_midnight.astimezone(timezone.utc) - timedelta(seconds=1)
        monday = local_midnight.astimezone(timezone.utc)
        wednesday = datetime(2026, 10, 21, 18, tzinfo=self.timezone).astimezone(
            timezone.utc
        )
        today = self.now.astimezone(self.timezone)
        store = self.database.collection(ORDER_COLLECTION).store
        store["old"] = self._order("old", before_week, total=50)
        store["monday"] = self._order(
            "monday",
            monday,
            total=12.35,
            items=[{"name": "Garden Margherita", "quantity": 2}],
        )
        store["cancelled"] = self._order(
            "cancelled",
            wednesday,
            status="Cancelled",
            total=90,
        )
        store["failed"] = self._order(
            "failed",
            wednesday,
            status="Failed",
            total=80,
        )
        store["today"] = self._order(
            "today",
            today.astimezone(timezone.utc),
            status="Delivered",
            total=20.10,
            delivery_simulation_id="mission-one",
            delivery_simulation_state="delivered",
        )

        result = analytics.load_order_analytics(
            now=self.now,
            timezone_name="America/Los_Angeles",
            currency="inr",
        )

        self.assertEqual(result["total_orders"], 5)
        self.assertEqual(result["orders_this_week"], 4)
        self.assertEqual(result["orders_today"], 1)
        self.assertEqual(result["order_value_this_week"], 32.45)
        self.assertEqual(result["currency"], "INR")
        self.assertEqual(
            next(day for day in result["daily"] if day["date"] == "2026-10-19")[
                "orders"
            ],
            1,
        )
        self.assertEqual(result["popular_dishes"], [
            {"name": "Garden Margherita", "quantity": 3},
        ])
        self.assertEqual(result["robot_completion"], {
            "completed": 1,
            "failed": 0,
            "total": 1,
            "percent": 100.0,
        })
        self.assertIsNone(result["average_delivery_minutes"])

    def test_status_change_removes_cancelled_order_value_but_keeps_order_count(self):
        store = self.database.collection(ORDER_COLLECTION).store
        store["order-one"] = self._order(
            "order-one",
            self.now - timedelta(minutes=2),
            total=42.75,
        )

        placed = analytics.load_order_analytics(
            now=self.now,
            timezone_name="UTC",
        )
        store["order-one"]["status"] = "Cancelled"
        cancelled = analytics.load_order_analytics(
            now=self.now,
            timezone_name="UTC",
        )

        self.assertEqual(placed["orders_this_week"], 1)
        self.assertEqual(placed["order_value_this_week"], 42.75)
        self.assertEqual(cancelled["orders_this_week"], 1)
        self.assertEqual(cancelled["order_value_this_week"], 0)
        self.assertEqual(cancelled["popular_dishes"], [])

    def test_failed_orders_and_duplicate_events_are_excluded_safely(self):
        order = self._order(
            "same-order",
            self.now,
            total=19.99,
            delivery_simulation_id="mission-failed",
            delivery_simulation_state="failed",
        )
        result = analytics.aggregate_order_analytics(
            [order, dict(order)],
            1,
            self.now,
            "UTC",
            None,
        )

        self.assertEqual(result["orders_today"], 1)
        self.assertEqual(result["order_value_this_week"], 19.99)
        self.assertEqual(result["popular_dishes"][0]["quantity"], 1)
        self.assertEqual(result["robot_completion"], {
            "completed": 0,
            "failed": 1,
            "total": 1,
            "percent": 0.0,
        })

    def test_invalid_totals_and_unknown_statuses_are_not_counted_as_order_value(self):
        orders = [
            self._order("bad-total", self.now, total="not-a-number"),
            self._order("unknown-status", self.now, status="Awaiting Payment"),
            self._order("negative-total", self.now, total=-50),
        ]

        result = analytics.aggregate_order_analytics(
            orders,
            len(orders),
            self.now,
            "UTC",
            None,
        )

        self.assertEqual(result["orders_today"], 3)
        self.assertEqual(result["order_value_this_week"], 0)
        self.assertEqual(result["popular_dishes"], [])

    def test_invalid_timezone_or_currency_is_reported(self):
        with self.assertRaises(analytics.AnalyticsConfigurationError):
            analytics.aggregate_order_analytics(
                [],
                0,
                self.now,
                "Not/A_Real_Zone",
                None,
            )
        with self.assertRaises(analytics.AnalyticsConfigurationError):
            analytics.aggregate_order_analytics(
                [],
                0,
                self.now,
                "UTC",
                "US Dollars",
            )


class AdminAnalyticsApiTests(unittest.TestCase):

    def setUp(self):
        self.config_patch = patch.dict(
            app_module.app.config,
            {
                "TESTING": True,
                "FIREBASE_ADMIN_UIDS": {"analytics-admin"},
            },
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.client = app_module.app.test_client()
        self.client.set_cookie("admin_session", "test-session")
        self.auth_patch = patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "analytics-admin"},
        )
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "analytics.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)

    def test_analytics_api_returns_live_data_shape_and_page_has_no_samples(self):
        page = self.client.get("/admin/analytics")
        response = self.client.get("/api/admin/analytics")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b"FIRESTORE ANALYTICS", page.data)
        self.assertNotIn(b"Sample statistics", page.data)
        self.assertNotIn(b"842", page.data)
        self.assertNotIn(b"$28,460", page.data)
        self.assertNotIn(b"Demo data", page.data)
        self.assertNotIn(b"Changes are not permanently saved", page.data)
        self.assertNotIn(b"DEMO PREVIEW", page.data)
        self.assertNotIn(b"USD", page.data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.is_json)
        self.assertTrue(response.content_type.startswith("application/json"))
        payload = response.get_json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["total_orders"], 0)
        self.assertEqual(len(payload["daily"]), 7)

    def test_analytics_api_requires_admin_authentication(self):
        self.client.delete_cookie("admin_session")

        response = self.client.get("/api/admin/analytics")

        self.assertEqual(response.status_code, 401)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json(),
            {"success": False, "error": "Admin sign-in is required."},
        )

    def test_analytics_api_reports_firestore_failure_without_fake_values(self):
        with patch(
            "analytics.get_firestore_client",
            side_effect=GoogleAPICallError("private firestore details"),
        ):
            response = self.client.get("/api/admin/analytics")

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json()["error"],
            "Analytics data is temporarily unavailable.",
        )
        self.assertNotIn(
            "private firestore details",
            response.get_data(as_text=True),
        )

    def test_analytics_api_returns_json_when_count_aggregation_shape_is_invalid(self):
        with patch(
            "analytics._aggregation_count_value",
            side_effect=analytics.AnalyticsDataError(
                "private aggregation details",
            ),
        ):
            response = self.client.get("/api/admin/analytics")

        self.assertEqual(response.status_code, 503)
        self.assertTrue(response.is_json)
        self.assertEqual(
            response.get_json()["error"],
            "Analytics data is temporarily unavailable.",
        )
        self.assertNotIn(
            "private aggregation details",
            response.get_data(as_text=True),
        )


if __name__ == "__main__":
    unittest.main()
