import asyncio
import unittest
from pathlib import Path

from fastapi import HTTPException

from apps.admin import views as admin_views
from apps.admin.schemas import LoginData
from apps.base.dependencies import IPRateLimit
from apps.base.file_validation import detect_file_kind, validate_file_magic, validate_file_type
from apps.base.utils import ip_limit
from core.settings import settings
from core.utils import hash_password


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class MagicBytesTests(SettingsOverrideMixin, unittest.TestCase):
    def test_detects_common_signatures(self):
        self.assertEqual(detect_file_kind(b"\x89PNG\r\n\x1a\nxxxx").name, "png")
        self.assertEqual(detect_file_kind(b"\xff\xd8\xff\xe0xxxx").name, "jpg")
        self.assertEqual(detect_file_kind(b"%PDF-1.7").name, "pdf")
        self.assertEqual(detect_file_kind(b"PK\x03\x04xxxx").name, "zip")
        self.assertEqual(detect_file_kind(b"RIFF\x00\x00\x00\x00WEBPxxxx").name, "webp")
        self.assertEqual(detect_file_kind(b"\x00\x00\x00\x18ftypmp42").name, "mp4")

    def test_rejects_extension_spoofing(self):
        settings.allowed_file_types = ["*"]
        with self.assertRaises(HTTPException) as ctx:
            validate_file_magic("photo.png", "image/png", b"MZ" + b"\x00" * 20)
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertIn("扩展名", ctx.exception.detail)

    def test_rejects_content_type_spoofing(self):
        settings.allowed_file_types = ["*"]
        with self.assertRaises(HTTPException) as ctx:
            validate_file_magic("blob.bin", "image/png", b"MZ" + b"\x00" * 20)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_accepts_matching_png(self):
        settings.allowed_file_types = [".png", "image/*"]
        validate_file_magic("a.png", "image/png", b"\x89PNG\r\n\x1a\nxxxx")

    def test_whitelist_still_enforced(self):
        settings.allowed_file_types = [".png"]
        with self.assertRaises(HTTPException):
            validate_file_type("a.exe", "application/x-msdownload")


class LoginRateLimitTests(SettingsOverrideMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        settings.admin_token = hash_password("correct-password-123")
        settings.jwt_secret = "j" * 48
        settings.loginCount = 3
        settings.loginMinute = 15
        self._original_login_limiter = ip_limit["login"]
        ip_limit["login"] = IPRateLimit(count=3, minutes=15)

    def tearDown(self):
        ip_limit["login"] = self._original_login_limiter
        super().tearDown()

    def test_failed_logins_are_rate_limited(self):
        async def attempt(password: str):
            return await admin_views.login(
                data=LoginData(password=password), ip="203.0.113.10"
            )

        for _ in range(3):
            with self.assertRaises(HTTPException) as ctx:
                asyncio.run(attempt("wrong-password"))
            self.assertEqual(ctx.exception.status_code, 401)

        self.assertFalse(ip_limit["login"].check_ip("203.0.113.10"))

    def test_successful_login_does_not_consume_failure_quota(self):
        result = asyncio.run(
            admin_views.login(
                data=LoginData(password="correct-password-123"), ip="198.51.100.8"
            )
        )
        self.assertIn("token", result.detail)
        self.assertTrue(ip_limit["login"].check_ip("198.51.100.8"))


class DockerNonRootTests(unittest.TestCase):
    def test_dockerfile_runs_as_non_root_user(self):
        text = Path("Dockerfile").read_text()
        self.assertIn("USER appuser", text)
        self.assertIn("--uid 1000", text)
        compose = Path("docker-compose.yml").read_text()
        self.assertIn('user: "1000:1000"', compose)


if __name__ == "__main__":
    unittest.main()
