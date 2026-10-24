import unittest
from unittest.mock import patch

import app
from src.instruction_parser import parse_instruction


class InstructionParserTests(unittest.TestCase):

    def test_delivery_instruction_uses_fast_local_parser(self):
        with patch(
            "src.instruction_parser.gemini_parser",
            side_effect=AssertionError("Gemini should not be called"),
        ):
            result = parse_instruction(
                "Deliver the water bottle to table 2."
            )

        self.assertEqual(result["intent"], "DELIVERY")
        self.assertEqual(result["item"], "water bottle")
        self.assertEqual(result["target"], "table 2")
        self.assertEqual(result["actions"], ["PICK", "PLACE"])

    def test_delivery_parser_accepts_singular_glass(self):
        with patch(
            "src.instruction_parser.gemini_parser",
            side_effect=AssertionError("Gemini should not be called"),
        ):
            result = parse_instruction(
                "Deliver one glass to table 3."
            )

        self.assertEqual(result["orders"][0]["table"], 3)
        self.assertEqual(
            result["orders"][0]["items"],
            [{
                "name": "glass",
                "quantity": 1,
                "status": "VALIDATED",
                "delivery_status": "PENDING",
                "delivered_quantity": 0,
            }],
        )

    def test_table_navigation_uses_fast_local_parser(self):
        with patch(
            "src.instruction_parser.gemini_parser",
            side_effect=AssertionError("Gemini should not be called"),
        ):
            result = parse_instruction(
                "Go to table 4."
            )

        self.assertEqual(result["intent"], "NAVIGATE")
        self.assertEqual(result["target"], "table 4")

    def test_unknown_delivery_item_still_uses_gemini(self):
        expected = {
            "intent": "DELIVERY",
            "actions": ["PICK", "PLACE"],
            "color": "",
            "object": "soup",
            "item": "soup",
            "quantity": 1,
            "original_instruction": "Deliver soup to table 2.",
            "target": "table 2",
        }

        with patch(
            "src.instruction_parser.gemini_parser",
            return_value=expected,
        ) as gemini_parser:
            result = parse_instruction(
                "Deliver soup to table 2."
            )

        gemini_parser.assert_called_once_with(
            "Deliver soup to table 2."
        )
        self.assertEqual(result, expected)


class InvalidTableRequestTests(unittest.TestCase):

    def setUp(self):
        self.admin_config_patch = patch.dict(
            app.app.config,
            {"TESTING": True, "FIREBASE_ADMIN_UIDS": {"test-admin"}},
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

    def test_nonexistent_table_is_rejected_before_execution(self):
        with (
            patch(
                "src.instruction_parser.gemini_parser",
                side_effect=AssertionError(
                    "Recognized instruction should use local parser"
                ),
            ),
            patch(
                "app.decompose_task",
                side_effect=AssertionError(
                    "Invalid table must be rejected before execution"
                ),
            ),
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
            response.get_json()["error"],
            "Table 8 does not exist. Available tables are 1, 2, 3, and 4. "
            "Please select a valid table.",
        )
        self.assertEqual(
            response.get_json()["robot_response"],
            "Table 8 does not exist. Available tables are 1, 2, 3, and 4. "
            "Please select a valid table.",
        )