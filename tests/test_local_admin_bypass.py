import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app as app_module


class LocalAdminAuthenticationTests(unittest.TestCase):

    def setUp(self):
        self.config_patch = patch.dict(
            app_module.app.config,
            {
                "TESTING": True,
                "DEBUG": True,
                "SECRET_KEY": "test-only-secret-key",
                "FIREBASE_ADMIN_UIDS": "",
            },
        )
        self.config_patch.start()
        self.addCleanup(self.config_patch.stop)
        self.client = app_module.app.test_client()

    def test_legacy_bypass_flag_still_shows_login_and_protects_admin_routes(self):
        with patch.dict(os.environ, {"ENABLE_LOCAL_ADMIN_BYPASS": "true"}):
            login = self.client.get(
                "/admin-login",
                base_url="http://127.0.0.1",
            )
            dashboard = self.client.get(
                "/admin",
                base_url="http://127.0.0.1",
            )
            simulation = self.client.get(
                "/simulation",
                base_url="http://127.0.0.1",
            )
            voice_camera = self.client.get(
                "/voice-camera",
                base_url="http://127.0.0.1",
            )

        self.assertEqual(login.status_code, 200)
        self.assertIn(b"Welcome back", login.data)
        self.assertIn(b"Sign in securely", login.data)
        self.assertNotIn(b"data-admin-next-path", login.data)
        self.assertIn(b"window.firebaseAuthConfig =", login.data)
        for response in (dashboard, voice_camera):
            self.assertEqual(response.status_code, 302)
            self.assertIn("/admin-login", response.headers["Location"])
        self.assertEqual(simulation.status_code, 302)
        self.assertIn("/admin-login", simulation.headers["Location"])

    def test_local_password_must_be_verified_before_dashboard_access(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_LOCAL_ADMIN_BYPASS": "true",
                "FLASK_LOCAL_ADMIN": "true",
                "LOCAL_ADMIN_PASSWORD": "test-local-password",
            },
        ):
            login = self.client.get(
                "/admin-login",
                base_url="http://127.0.0.1",
            )
            self.assertEqual(login.status_code, 200)
            self.assertIn(b"Local development password", login.data)

            wrong_password = self.client.post(
                "/api/admin/local-session",
                json={"password": "wrong-password"},
                headers={"Origin": "http://127.0.0.1"},
                base_url="http://127.0.0.1",
            )
            dashboard_before_login = self.client.get(
                "/admin",
                base_url="http://127.0.0.1",
            )
            valid_password = self.client.post(
                "/api/admin/local-session",
                json={"password": "test-local-password"},
                headers={"Origin": "http://127.0.0.1"},
                base_url="http://127.0.0.1",
            )
            dashboard_after_login = self.client.get(
                "/admin",
                base_url="http://127.0.0.1",
            )

        self.assertEqual(wrong_password.status_code, 401)
        self.assertEqual(dashboard_before_login.status_code, 302)
        self.assertEqual(valid_password.status_code, 200)
        self.assertEqual(dashboard_after_login.status_code, 200)
        self.assertIn(b"Restaurant overview", dashboard_after_login.data)

    def test_local_password_login_is_rejected_for_remote_request(self):
        with patch.dict(
            os.environ,
            {
                "FLASK_LOCAL_ADMIN": "true",
                "LOCAL_ADMIN_PASSWORD": "test-local-password",
            },
        ):
            response = self.client.post(
                "/api/admin/local-session",
                json={"password": "test-local-password"},
                headers={"Origin": "http://192.0.2.10"},
                base_url="http://192.0.2.10",
                environ_base={"REMOTE_ADDR": "192.0.2.10"},
            )

        self.assertEqual(response.status_code, 403)

    def test_ipv6_loopback_displays_login_without_skipping_authentication(self):
        with patch.dict(os.environ, {"ENABLE_LOCAL_ADMIN_BYPASS": "true"}):
            login = self.client.get(
                "/admin-login",
                base_url="http://[::1]",
                environ_base={"REMOTE_ADDR": "::1"},
            )
            dashboard = self.client.get(
                "/admin",
                base_url="http://[::1]",
                environ_base={"REMOTE_ADDR": "::1"},
            )

        self.assertEqual(login.status_code, 200)
        self.assertIn(b"Welcome back", login.data)
        self.assertEqual(dashboard.status_code, 302)
        self.assertIn("/admin-login", dashboard.headers["Location"])

    def test_firebase_authentication_remains_required_when_local_mode_is_disabled(self):
        response = self.client.get("/admin", base_url="http://127.0.0.1")

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin-login", response.headers["Location"])

    def test_legacy_bypass_flag_does_not_change_server_auth_binding(self):
        with patch.dict(
            os.environ,
            {
                "ENABLE_LOCAL_ADMIN_BYPASS": "true",
                "FLASK_HOST": "0.0.0.0",
                "FLASK_DEBUG": "1",
                "PORT": "5000",
            },
        ):
            startup_config = app_module._server_startup_config()

        self.assertEqual(startup_config, ("0.0.0.0", 5000, False))

    def test_non_loopback_server_binding_requires_https(self):
        for host in ("0.0.0.0", "10.16.246.64", "restaurant.local"):
            with self.subTest(host=host), self.assertRaisesRegex(
                RuntimeError,
                "without HTTPS",
            ):
                app_module._validate_server_transport(host, None)

        for host in ("127.0.0.1", "localhost", "::1"):
            with self.subTest(host=host):
                app_module._validate_server_transport(host, None)

        app_module._validate_server_transport(
            "10.0.0.25",
            ("certificate.pem", "private-key.pem"),
        )

    def test_public_demo_requires_loopback_and_matching_quick_tunnel_url(self):
        with (
            patch.dict(os.environ, {
                "PUBLIC_DEMO_MODE": "true",
                "PUBLIC_DEMO_URL": "https://demo-123.trycloudflare.com",
                "QR_BASE_URL": "https://demo-123.trycloudflare.com",
            }),
            patch.object(app_module, "trusted_proxy_hops", 1),
        ):
            app_module._validate_server_transport("127.0.0.1", None)
            with self.assertRaisesRegex(RuntimeError, "without HTTPS"):
                app_module._validate_server_transport("0.0.0.0", None)

        with (
            patch.dict(os.environ, {
                "PUBLIC_DEMO_MODE": "true",
                "PUBLIC_DEMO_URL": "https://demo-123.trycloudflare.com",
                "QR_BASE_URL": "https://other.trycloudflare.com",
            }),
            patch.object(app_module, "trusted_proxy_hops", 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "same HTTPS"):
                app_module._validate_server_transport("127.0.0.1", None)

    def test_browser_entry_is_always_admin_login(self):
        for bypass_enabled in ("true", "false"):
            with self.subTest(bypass_enabled=bypass_enabled), patch.dict(
                os.environ,
                {"ENABLE_LOCAL_ADMIN_BYPASS": bypass_enabled},
            ):
                self.assertEqual(
                    app_module._admin_browser_path(),
                    "/admin-login",
                )

    def test_default_server_browser_url_opens_admin_login_on_loopback(self):
        self.assertEqual(
            app_module._admin_browser_url(5000),
            "http://127.0.0.1:5000/admin-login",
        )
        self.assertEqual(
            app_module._admin_browser_url(5000, secure=True),
            "https://127.0.0.1:5000/admin-login",
        )

    def test_local_tls_requires_a_certificate_and_private_key_pair(self):
        with patch.dict(
            os.environ,
            {"FLASK_TLS_CERT_FILE": "", "FLASK_TLS_KEY_FILE": ""},
        ):
            self.assertIsNone(app_module._server_ssl_context())

        with tempfile.TemporaryDirectory() as temporary_directory:
            certificate = Path(temporary_directory) / "lan-cert.pem"
            private_key = Path(temporary_directory) / "lan-key.pem"
            certificate.touch()
            private_key.touch()
            with patch.dict(
                os.environ,
                {
                    "FLASK_TLS_CERT_FILE": str(certificate),
                    "FLASK_TLS_KEY_FILE": str(private_key),
                },
            ):
                self.assertEqual(
                    app_module._server_ssl_context(),
                    (str(certificate), str(private_key)),
                )

        with patch.dict(
            os.environ,
            {
                "FLASK_TLS_CERT_FILE": "certificate.pem",
                "FLASK_TLS_KEY_FILE": "",
            },
        ):
            with self.assertRaisesRegex(RuntimeError, "Set both"):
                app_module._server_ssl_context()

    def test_debug_reloader_opens_browser_only_in_serving_process(self):
        with patch.dict(os.environ):
            os.environ.pop("WERKZEUG_RUN_MAIN", None)
            self.assertFalse(app_module._should_open_admin_browser(True))
            self.assertTrue(app_module._should_open_admin_browser(False))

        with patch.dict(os.environ, {"WERKZEUG_RUN_MAIN": "true"}):
            self.assertTrue(app_module._should_open_admin_browser(True))
