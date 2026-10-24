import unittest
from collections import Counter
from unittest.mock import patch

import app
from integrated_pipeline import run_pipeline
from src.instruction_parser import parse_instruction


class MultiOrderParserTests(unittest.TestCase):

    def test_multiple_items_and_quantities_for_one_table(self):
        parsed = parse_instruction(
            "Deliver 2 water bottles and 3 plates of food to Table 2."
        )

        self.assertEqual(len(parsed["orders"]), 1)
        self.assertEqual(parsed["orders"][0]["table"], 2)
        self.assertEqual(
            parsed["orders"][0]["items"],
            [
                {
                    "name": "water bottle",
                    "quantity": 2,
                    "status": "VALIDATED",
                    "delivery_status": "PENDING",
                    "delivered_quantity": 0,
                },
                {
                    "name": "plate of food",
                    "quantity": 3,
                    "status": "VALIDATED",
                    "delivery_status": "PENDING",
                    "delivered_quantity": 0,
                },
            ],
        )

    def test_words_plural_and_multiple_tables_are_separated(self):
        parsed = parse_instruction(
            "Take one burger, two pizzas, and three cold drinks to Table 4."
        )

        self.assertEqual(
            [
                (item["name"], item["quantity"])
                for item in parsed["orders"][0]["items"]
            ],
            [("burger", 1), ("pizza", 2), ("cold drink", 3)],
        )

        parsed = parse_instruction(
            "Deliver 2 water bottles to Table 1 and 3 burgers to Table 2."
        )
        self.assertEqual(
            [
                (
                    order["table"],
                    [
                        (item["name"], item["quantity"])
                        for item in order["items"]
                    ],
                )
                for order in parsed["orders"]
            ],
            [
                (1, [("water bottle", 2)]),
                (2, [("burger", 3)]),
            ],
        )

    def test_unassigned_items_require_a_destination(self):
        parsed = parse_instruction(
            "Deliver water to Table 1 and food."
        )

        self.assertEqual(parsed["orders"][-1]["table"], None)
        self.assertEqual(
            parsed["orders"][-1]["status"],
            "MISSING_DESTINATION",
        )


class MultiOrderExecutionTests(unittest.TestCase):

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

    def execute(self, instruction, robot):
        with patch("app.RobotController", return_value=robot):
            return self.client.post(
                "/process",
                json={"instruction": instruction},
            )

    def test_every_unit_runs_as_a_task_for_its_own_table(self):
        class RecordingRobot:
            def __init__(self):
                self.calls = []

            def execute_sequence(self, commands, object_name, target):
                self.calls.append((object_name, target))
                return {
                    "overall_status": "SUCCESS",
                    "results": [{
                        "step": 1,
                        "command": "DELIVER",
                        "status": "SUCCESS",
                        "message": "Delivery confirmed.",
                    }],
                }

        robot = RecordingRobot()
        response = self.execute(
            "Deliver 2 water bottles to Table 1 and 3 burgers to Table 2.",
            robot,
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertEqual(
            Counter(robot.calls),
            Counter({
                ("water bottle", "table 1"): 2,
                ("burger", "table 2"): 3,
            }),
        )
        self.assertEqual(
            [order["status"] for order in body["order_plan"]],
            ["DELIVERED", "DELIVERED"],
        )
        self.assertIn("Two water bottles were delivered to Table 1", body["robot_response"])
        self.assertIn("three burgers were delivered to Table 2", body["robot_response"])

    def test_invalid_table_prevents_all_robot_execution(self):
        with patch("app.RobotController") as robot_controller:
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver water to Table 1 and burgers to Table 8."
                },
            )

        self.assertEqual(response.status_code, 400)
        body = response.get_json()
        self.assertIn("Table 8 does not exist", body["robot_response"])
        self.assertEqual(body["order_plan"][1]["status"], "INVALID_TABLE")
        robot_controller.assert_not_called()

    def test_missing_destination_prevents_robot_execution(self):
        with patch("app.RobotController") as robot_controller:
            response = self.client.post(
                "/process",
                json={
                    "instruction":
                        "Deliver 2 water bottles and 3 burgers."
                },
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["robot_response"],
            "Please specify a destination table number.",
        )
        robot_controller.assert_not_called()

    def test_missing_items_prevent_robot_execution(self):
        parsed = {
            "intent": "DELIVERY",
            "actions": ["PICK", "PLACE"],
            "item": "",
            "object": "",
            "target": "table 2",
        }
        with (
            patch("app.parse_instruction", return_value=parsed),
            patch("app.RobotController") as robot_controller,
        ):
            response = self.client.post(
                "/process",
                json={"instruction": "Deliver to Table 2."},
            )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json()["robot_response"],
            "Please specify the items for delivery.",
        )
        robot_controller.assert_not_called()

    def test_failed_delivery_reports_item_and_table_without_claiming_delivery(self):
        class FailingTableRobot:
            def execute_sequence(self, commands, object_name, target):
                succeeded = target == "table 1"
                status = "SUCCESS" if succeeded else "FAILED"
                return {
                    "overall_status": status,
                    "results": [{
                        "step": 1,
                        "command": "DELIVER",
                        "status": status,
                        "message": (
                            "Delivery confirmed."
                            if succeeded
                            else "Delivery failed."
                        ),
                    }],
                }

        response = self.execute(
            "Deliver water to Table 1 and 3 burgers to Table 2.",
            FailingTableRobot(),
        )

        body = response.get_json()
        self.assertFalse(body["success"])
        self.assertEqual(body["order_plan"][0]["status"], "DELIVERED")
        self.assertEqual(body["order_plan"][1]["status"], "FAILED")
        self.assertIn("Delivery of three burgers to Table 2 failed", body["robot_response"])
        self.assertNotIn("Three burgers were delivered", body["robot_response"])

    def test_partial_quantity_is_not_marked_as_delivered(self):
        class OneUnitFailureRobot:
            def __init__(self):
                self.calls = 0

            def execute_sequence(self, commands, object_name, target):
                self.calls += 1
                succeeded = self.calls < 3
                status = "SUCCESS" if succeeded else "FAILED"
                return {
                    "overall_status": status,
                    "results": [{
                        "step": 1,
                        "command": "DELIVER",
                        "status": status,
                        "message": status,
                    }],
                }

        robot = OneUnitFailureRobot()
        response = self.execute(
            "Deliver 3 water bottles to Table 1.",
            robot,
        )

        body = response.get_json()
        item = body["order_plan"][0]["items"][0]
        self.assertFalse(body["success"])
        self.assertEqual(item["delivered_quantity"], 2)
        self.assertEqual(item["delivery_status"], "PARTIALLY_DELIVERED")
        self.assertEqual(
            body["order_plan"][0]["status"],
            "PARTIALLY_DELIVERED",
        )
        self.assertIn(
            "Delivery of two of three water bottles to Table 1",
            body["robot_response"],
        )
        self.assertNotIn(
            "three water bottles were delivered",
            body["robot_response"],
        )

    def test_integrated_pipeline_uses_the_multi_order_executor(self):
        class SuccessfulRobot:
            def execute_sequence(self, commands, object_name, target):
                return {
                    "overall_status": "SUCCESS",
                    "results": [{
                        "step": 1,
                        "command": "DELIVER",
                        "status": "SUCCESS",
                        "message": "Delivery confirmed.",
                    }],
                }

        with patch(
            "app.RobotController",
            return_value=SuccessfulRobot(),
        ):
            result = run_pipeline(
                "Deliver water to Table 1 and burger to Table 2."
            )

        self.assertTrue(result["success"])
        self.assertEqual(
            [order["table"] for order in result["order_plan"]],
            [1, 2],
        )
        self.assertEqual(
            [order["status"] for order in result["order_plan"]],
            ["DELIVERED", "DELIVERED"],
        )
