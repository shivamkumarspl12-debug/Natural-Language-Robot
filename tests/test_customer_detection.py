import io
import unittest
from unittest.mock import patch

import cv2
import numpy as np

import app


class CustomerDetectionTests(unittest.TestCase):

    def setUp(self):
        app.app.config["TESTING"] = True
        self.client = app.app.test_client()

    def jpeg_upload(self, frame):
        encoded, buffer = cv2.imencode(".jpg", frame)
        self.assertTrue(encoded)
        return {
            "frame": (io.BytesIO(buffer.tobytes()), "frame.jpg")
        }

    def test_missing_frame_returns_json_error(self):
        response = self.client.post("/detect-customer")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.get_json()["success"])

    def test_invalid_image_returns_json_error(self):
        response = self.client.post(
            "/detect-customer",
            data={
                "frame": (io.BytesIO(b"not an image"), "frame.jpg")
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("valid image", response.get_json()["error"])

    def test_blank_frame_is_not_reported_as_a_customer(self):
        response = self.client.post(
            "/detect-customer",
            data=self.jpeg_upload(np.zeros((240, 320, 3), dtype=np.uint8)),
        )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["success"])
        self.assertFalse(body["detected"])
        self.assertEqual(body["result"], "No Customer Detected")
        self.assertEqual(body["detections"], [])

    def test_positive_detection_returns_box_and_model_score(self):
        detector = unittest.mock.Mock()
        detector.infer.return_value = np.array(
            [[20, 30, 84, 158, 0, 0, 0, 0, 0, 0, 0, 0, 0.91]]
        )

        with patch("app._get_person_detector", return_value=(cv2, detector)):
            response = self.client.post(
                "/detect-customer",
                data=self.jpeg_upload(
                    np.zeros((240, 320, 3), dtype=np.uint8)
                ),
            )

        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertTrue(body["detected"])
        self.assertEqual(body["result"], "Customer Detected")
        self.assertEqual(
            body["detections"],
            [{
                "x": 20,
                "y": 30,
                "width": 64,
                "height": 128,
                "score": 0.91,
            }],
        )


if __name__ == "__main__":
    unittest.main()
