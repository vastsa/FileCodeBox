import asyncio
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from apps.admin import dependencies as admin_dependencies
from apps.admin.dependencies import create_token, verify_token
from apps.admin.services import LocalFileClass
from core.settings import data_root, settings
from core.storage import SystemFileStorage
from core.utils import hash_password, verify_password


class PasswordCompareTests(unittest.TestCase):
    def test_verify_password_accepts_valid_hash(self):
        hashed = hash_password("s3cret-pass")
        self.assertTrue(verify_password("s3cret-pass", hashed))
        self.assertFalse(verify_password("wrong-pass", hashed))

    def test_verify_password_supports_legacy_plaintext(self):
        self.assertTrue(verify_password("legacy", "legacy"))
        self.assertFalse(verify_password("legacy", "other"))


class LocalFilePathTraversalTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.local_root = Path(self._tmpdir.name) / "local"
        self.local_root.mkdir(parents=True, exist_ok=True)
        (self.local_root / "safe.txt").write_text("ok", encoding="utf-8")
        self._data_root_patch = patch(
            "apps.admin.services.data_root", Path(self._tmpdir.name)
        )
        self._data_root_patch.start()

    def tearDown(self):
        self._data_root_patch.stop()
        self._tmpdir.cleanup()

    def test_rejects_dotdot_filename(self):
        with self.assertRaises(HTTPException) as ctx:
            LocalFileClass("../etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_rejects_absolute_filename(self):
        with self.assertRaises(HTTPException) as ctx:
            LocalFileClass("/etc/passwd")
        self.assertEqual(ctx.exception.status_code, 400)

    def test_allows_basename_inside_local(self):
        local_file = LocalFileClass("safe.txt")
        self.assertTrue(asyncio.run(local_file.exists()))
        self.assertEqual(local_file.file, "safe.txt")
        self.assertEqual(local_file.path, (self.local_root / "safe.txt").resolve())


class SystemStoragePathTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.storage = SystemFileStorage()
        self.storage.root_path = Path(self._tmpdir.name)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_resolve_safe_path_blocks_escape(self):
        with self.assertRaises(ValueError):
            self.storage._resolve_safe_path("../etc/passwd")

    def test_resolve_safe_path_allows_nested(self):
        target = self.storage._resolve_safe_path("share/data/a/b.txt")
        self.assertTrue(str(target).startswith(str(Path(self._tmpdir.name).resolve())))


class AdminJwtUrlSafeTests(unittest.TestCase):
    def setUp(self):
        settings.jwt_secret = "j" * 48

    def test_create_and_verify_roundtrip(self):
        token = create_token({"is_admin": True}, expires_in=60)
        # urlsafe token 不应依赖标准 base64 填充字符
        self.assertNotIn("+", token)
        self.assertNotIn("/", token)
        payload = verify_token(token)
        self.assertTrue(payload["is_admin"])


if __name__ == "__main__":
    unittest.main()
