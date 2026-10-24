import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from PIL import Image

import app as app_module
from firestore_fakes import MemoryFirestore


class MenuManagementTests(unittest.TestCase):

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
        self.database = MemoryFirestore()
        self.firestore_patch = patch(
            "customer_orders.get_firestore_client",
            return_value=self.database,
        )
        self.firestore_patch.start()
        self.addCleanup(self.firestore_patch.stop)
        self.upload_folder = tempfile.TemporaryDirectory()
        app_module.app.config["MENU_UPLOAD_FOLDER"] = self.upload_folder.name
        self.addCleanup(self.upload_folder.cleanup)

    def admin_headers(self):
        return {"Origin": "http://localhost"}

    def upload_food_image(self, name):
        image_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), color="green").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        response = self.client.post(
            "/api/admin/menu-images",
            data={"image": (image_bytes, "food.png"), "name": name},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 201)
        return response.get_json()["image"]

    def test_public_customer_menu_read_does_not_seed_default_writes(self):
        public_response = self.client.get("/api/customer/menu")

        self.assertEqual(public_response.status_code, 200)
        self.assertEqual(public_response.get_json()["items"], [])
        self.assertEqual(
            set(self.database.collections),
            {"menu_items"},
        )
        self.assertEqual(self.database.collections["menu_items"], {})

        admin_response = self.client.get("/api/admin/menu")
        self.assertEqual(admin_response.status_code, 200)
        items = admin_response.get_json()["items"]
        self.assertEqual(len(items), 12)
        self.assertEqual(
            self.database.collections["menu_items"]["garden-margherita"]["name"],
            "Garden Margherita",
        )
        self.assertEqual(
            self.client.get("/api/customer/menu").get_json()["items"],
            items,
        )

    def test_admin_menu_crud_and_customer_polling_share_firestore_data(self):
        self.client.get("/api/admin/menu")
        payload = {
            "name": "Test Garden Bowl",
            "price": 13.25,
            "description": "Greens, grains, and herbs",
            "category": "Bowls",
            "available": True,
            "image": self.upload_food_image("Test Garden Bowl"),
        }
        created = self.client.post(
            "/api/admin/menu",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(created.status_code, 201)
        created_item = created.get_json()["item"]
        item_id = created_item["id"]
        self.assertEqual(created_item["price"], 13.25)

        public_items = self.client.get("/api/customer/menu").get_json()["items"]
        self.assertIn(created_item, public_items)

        payload["available"] = False
        changed = self.client.put(
            f"/api/admin/menu/{item_id}",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(changed.status_code, 200)
        self.assertFalse(changed.get_json()["item"]["available"])
        self.assertFalse(
            next(
                item
                for item in self.client.get("/api/customer/menu").get_json()["items"]
                if item["id"] == item_id
            )["available"]
        )

        order = self.client.post(
            "/api/customer/orders",
            json={
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 2,
                "items": [{"id": item_id, "quantity": 1}],
            },
            headers={
                "Origin": "http://localhost",
                "X-Order-Access-Token": "Q" * 43,
            },
        )
        self.assertEqual(order.status_code, 400)
        self.assertIn("unavailable", order.get_json()["error"].lower())

        deleted = self.client.delete(
            f"/api/admin/menu/{item_id}",
            headers=self.admin_headers(),
        )
        self.assertEqual(deleted.status_code, 200)
        self.assertNotIn(
            item_id,
            {
                item["id"]
                for item in self.client.get("/api/customer/menu").get_json()["items"]
            },
        )

    def test_available_menu_items_require_existing_name_matched_images(self):
        payload = {
            "name": "Garden Margherita",
            "price": 18.5,
            "description": "Tomato and basil",
            "category": "Pizza",
            "available": True,
            "image": "",
        }
        missing_image = self.client.post(
            "/api/admin/menu",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(missing_image.status_code, 400)

        mismatched_image = self.upload_food_image("Other Dish")
        payload["image"] = mismatched_image
        mismatched = self.client.post(
            "/api/admin/menu",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(mismatched.status_code, 400)

        payload["image"] = "uploads/garden-margherita-missing.png"
        nonexistent = self.client.post(
            "/api/admin/menu",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(nonexistent.status_code, 400)

        payload["image"] = self.upload_food_image("Garden Margherita")
        valid = self.client.post(
            "/api/admin/menu",
            json=payload,
            headers=self.admin_headers(),
        )
        self.assertEqual(valid.status_code, 201)

    def test_customer_order_attempt_does_not_seed_default_menu(self):
        response = self.client.post(
            "/api/customer/orders",
            json={
                "customer_name": "Jordan Guest",
                "customer_phone": "5035550188",
                "table_number": 2,
                "items": [{"id": "garden-margherita", "quantity": 1}],
            },
            headers={
                "Origin": "http://localhost",
                "X-Order-Access-Token": "Q" * 43,
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.database.collections.get("menu_items", {}), {})

    def test_menu_changes_require_admin_and_same_origin(self):
        unauthenticated = app_module.app.test_client().post(
            "/api/admin/menu",
            json={
                "name": "Blocked",
                "price": 2,
                "category": "Test",
                "available": True,
            },
        )
        self.assertEqual(unauthenticated.status_code, 401)

        cross_origin = self.client.post(
            "/api/admin/menu",
            json={
                "name": "Blocked",
                "price": 2,
                "category": "Test",
                "available": True,
            },
            headers={"Origin": "https://attacker.example"},
        )
        self.assertEqual(cross_origin.status_code, 403)

    def test_local_image_upload_validates_content_and_keeps_previous_files(self):
        image_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), color="green").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        uploaded = self.client.post(
            "/api/admin/menu-images",
            data={"image": (image_bytes, "menu-dish.png"), "name": "Test Dish"},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(uploaded.status_code, 201)
        first_result = uploaded.get_json()
        self.assertRegex(first_result["image"], r"^uploads/test-dish-[a-f0-9]{8}\.png$")
        first_file = Path(self.upload_folder.name) / Path(first_result["image"]).name
        self.assertTrue(first_file.is_file())

        image_bytes = io.BytesIO()
        Image.new("RGB", (4, 4), color="red").save(image_bytes, format="PNG")
        image_bytes.seek(0)
        replaced = self.client.post(
            "/api/admin/menu-images",
            data={"image": (image_bytes, "replace.png"), "name": "Replacement Dish"},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(replaced.status_code, 201)
        self.assertTrue(first_file.is_file())
        self.assertTrue(
            (Path(self.upload_folder.name) / Path(replaced.get_json()["image"]).name).is_file()
        )

    def test_image_upload_rejects_invalid_extension_content_and_size(self):
        invalid_extension = self.client.post(
            "/api/admin/menu-images",
            data={"image": (io.BytesIO(b"image"), "dish.gif"), "name": "Dish"},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(invalid_extension.status_code, 400)

        fake_image = self.client.post(
            "/api/admin/menu-images",
            data={"image": (io.BytesIO(b"not an image"), "dish.png"), "name": "Dish"},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(fake_image.status_code, 400)

        oversized = self.client.post(
            "/api/admin/menu-images",
            data={"image": (io.BytesIO(b"x" * (5 * 1024 * 1024 + 1)), "large.png"), "name": "Dish"},
            headers=self.admin_headers(),
            content_type="multipart/form-data",
        )
        self.assertEqual(oversized.status_code, 413)

    def test_image_upload_is_authenticated(self):
        response = app_module.app.test_client().post(
            "/api/admin/menu-images",
            data={"image": (io.BytesIO(b"image"), "dish.png")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 401)


if __name__ == "__main__":
    unittest.main()
