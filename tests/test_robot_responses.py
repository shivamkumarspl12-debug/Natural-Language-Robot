import unittest
from unittest.mock import patch

import app


class RobotResponseTests(unittest.TestCase):

    def setUp(self):
        app.app.config["TESTING"] = True
        self.admin_config_patch = patch.dict(
            app.app.config,
            {"FIREBASE_ADMIN_UIDS": {"test-admin"}},
        )
        self.admin_config_patch.start()
        self.addCleanup(self.admin_config_patch.stop)
        self.auth_patch = patch(
            "app.firebase_auth.verify_session_cookie",
            return_value={"uid": "test-admin"},
        )
        self.auth_patch.start()
        self.addCleanup(self.auth_patch.stop)
        self.client = app.app.test_client()
        self.client.set_cookie("admin_session", "test-session")

    def test_robot_instruction_endpoint_requires_admin_session(self):
        response = app.app.test_client().post(
            "/process",
            json={"instruction": "Deliver water to table 1."},
        )

        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.get_json()["success"])

    def test_simulation_view_is_admin_protected_and_customer_pages_remain_public(self):
        client = app.app.test_client()
        simulation = client.get("/simulation")
        self.assertEqual(simulation.status_code, 302)
        self.assertIn("/admin-login", simulation.headers["Location"])

        admin_simulation = self.client.get("/simulation")
        self.assertEqual(admin_simulation.status_code, 200)
        self.assertIn(b"SIMULATION ONLY", admin_simulation.data)
        self.assertIn(b"mission-order-id", admin_simulation.data)
        self.assertIn(b"/api/admin/simulation/orders", admin_simulation.data)
        self.assertIn(b"publishSimulationPosition(now)", admin_simulation.data)
        self.assertIn(b"/static/js/restaurant_navigation.js", admin_simulation.data)
        self.assertIn(b"createReturnRoute(robot.position)", admin_simulation.data)
        self.assertNotIn(b"Water Bottle", admin_simulation.data)

        response = client.get("/voice-camera")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login", response.headers["Location"])
        customer_response = client.get("/customer/menu?table=1")
        self.assertEqual(customer_response.status_code, 200)
        customer_tracking_page = client.get("/customer/order-status?table=1")
        self.assertEqual(customer_tracking_page.status_code, 200)
        self.assertIn(b"SOFTWARE SIMULATION", customer_tracking_page.data)
        self.assertNotIn(b"Battery", customer_tracking_page.data)
        self.assertNotIn(b"System Event Log", customer_tracking_page.data)

    def test_customer_robot_tracking_page_is_mobile_ready_and_has_no_admin_controls(self):
        client = app.app.test_client()
        page = client.get("/customer/robot-tracking?table=3")

        self.assertEqual(page.status_code, 200)
        self.assertIn(b'name="viewport"', page.data)
        self.assertIn(b"SIMULATED DELIVERY", page.data)
        self.assertIn(b"robotScene", page.data)
        self.assertIn(b"not a physical robot", page.data)
        self.assertNotIn(b"Start", page.data)
        self.assertNotIn(b"Pause", page.data)
        self.assertNotIn(b"Battery", page.data)
        self.assertNotIn(b"retry_count", page.data)
        self.assertNotIn(b"System Event Log", page.data)

        script = client.get("/static/js/customer_robot_tracking.js")
        stylesheet = client.get("/static/css/customer_robot_tracking.css")
        self.assertEqual(script.status_code, 200)
        self.assertEqual(stylesheet.status_code, 200)
        self.assertIn(b"/api/customer/orders/", script.data)
        self.assertIn(b"X-Order-Access-Token", script.data)
        self.assertIn(b"ResizeObserver", script.data)
        self.assertIn(b"setInterval(refresh, 5000)", script.data)
        self.assertIn(b"max-width: 700px", stylesheet.data)
        script.close()
        stylesheet.close()

        customer_navigation = client.get("/customer/menu")
        self.assertIn(b"/customer/robot-tracking", customer_navigation.data)
        self.assertNotIn(b'href="/simulation">3D Robot Simulation', customer_navigation.data)

    def parsed_instruction(self, target, intent="DELIVERY"):
        return {
            "intent": intent,
            "actions": ["PICK", "PLACE"],
            "color": "",
            "object": "water bottle",
            "item": "water bottle",
            "quantity": 1,
            "original_instruction":
                f"Deliver the water bottle to {target}.",
            "target": target,
        }

    def test_invalid_table_is_rejected_before_robot_execution(self):
        with (
            patch(
                "app.parse_instruction",
                return_value=self.parsed_instruction("table 8"),
            ),
            patch("app.RobotController") as robot_controller,
        ):
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver the water bottle to table 8."
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["robot_response"],
            "Table 8 does not exist. Available tables are 1, 2, 3, and 4. "
            "Please select a valid table.",
        )
        robot_controller.assert_not_called()

    def test_missing_destination_is_rejected_before_robot_execution(self):
        with (
            patch(
                "app.parse_instruction",
                return_value=self.parsed_instruction(""),
            ),
            patch("app.RobotController") as robot_controller,
        ):
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver the water bottle."
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["robot_response"],
            "Please specify a destination table number.",
        )
        robot_controller.assert_not_called()

    def test_success_response_is_only_returned_after_execution_succeeds(self):
        execution = {
            "overall_status": "SUCCESS",
            "robot_status": "READY",
            "current_location": "COUNTER",
            "battery": 100,
            "results": [
                {
                    "step": 1,
                    "command": "DELIVER",
                    "status": "SUCCESS",
                    "message": "Delivery completed.",
                    "attempts": 1,
                }
            ],
        }
        robot = app.RobotController()
        robot.execute_sequence = lambda *args, **kwargs: execution

        with (
            patch(
                "app.parse_instruction",
                return_value=self.parsed_instruction("table 4"),
            ),
            patch(
                "app.decompose_task",
                return_value=[{"step": 1, "task": "DELIVERY"}],
            ),
            patch(
                "app.generate_action_sequence",
                return_value=[
                    {"step": 1, "action": "DELIVER"}
                ],
            ),
            patch("app.RobotController", return_value=robot),
        ):
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver the water bottle to table 4."
                },
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(
            body["robot_response"],
            "Your instruction is valid. Delivering the water bottle to Table 4.",
        )

    def test_failed_execution_does_not_announce_delivery(self):
        execution = {
            "overall_status": "FAILED",
            "robot_status": "ERROR",
            "current_location": "COUNTER",
            "battery": 100,
            "results": [
                {
                    "step": 1,
                    "command": "DELIVER",
                    "status": "FAILED",
                    "message": "Delivery failed.",
                    "attempts": 3,
                }
            ],
        }
        robot = app.RobotController()
        robot.execute_sequence = lambda *args, **kwargs: execution

        with (
            patch(
                "app.parse_instruction",
                return_value=self.parsed_instruction("table 4"),
            ),
            patch(
                "app.decompose_task",
                return_value=[{"step": 1, "task": "DELIVERY"}],
            ),
            patch(
                "app.generate_action_sequence",
                return_value=[
                    {"step": 1, "action": "DELIVER"}
                ],
            ),
            patch("app.RobotController", return_value=robot),
        ):
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver the water bottle to table 4."
                },
            )

        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertEqual(
            body["robot_response"],
            "Sorry, I could not process your instruction. Please try again.",
        )
