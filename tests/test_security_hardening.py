import asyncio
from io import BytesIO
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException
from starlette.datastructures import UploadFile
from tortoise import Tortoise

from apps.base import views
from apps.admin import dependencies as admin_dependencies
from apps.admin.dependencies import create_token, verify_token
from apps.admin.services import LocalFileClass
from apps.base.models import FileCodes, UploadChunk
from apps.base.schemas import CompleteUploadModel, InitChunkUploadModel
from apps.base.utils import get_chunk_file_path_name
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

    def test_resolve_safe_path_blocks_internal_dotdot(self):
        with self.assertRaises(ValueError):
            self.storage._resolve_safe_path("share/data/2026/08/29/x/../../../../../../filecodebox.db")

    def test_resolve_safe_path_blocks_windows_dotdot(self):
        with self.assertRaises(ValueError):
            self.storage._resolve_safe_path("share\\data\\..\\..\\filecodebox.db")

    def test_resolve_safe_path_allows_nested(self):
        target = self.storage._resolve_safe_path("share/data/a/b.txt")
        self.assertTrue(str(target).startswith(str(Path(self._tmpdir.name).resolve())))


class ChunkFileNameSanitizeTests(unittest.TestCase):
    def test_chunk_file_path_name_strips_traversal(self):
        path, _, _, filename, save_path = asyncio.run(
            get_chunk_file_path_name("../../../../../../filecodebox.db", "a" * 32)
        )
        self.assertNotIn("..", save_path)
        self.assertEqual(filename, "filecodebox.db")
        self.assertEqual(save_path, f"{path}/filecodebox.db")
        self.assertIn("a" * 32, path)

    def test_chunk_file_path_name_strips_windows_traversal(self):
        _, _, _, filename, save_path = asyncio.run(
            get_chunk_file_path_name("..\\..\\..\\..\\..\\..\\evil.bin", "b" * 32)
        )
        self.assertNotIn("..", save_path)
        self.assertEqual(filename, "evil.bin")

    def test_chunk_file_path_name_keeps_normal_name(self):
        _, _, _, filename, save_path = asyncio.run(
            get_chunk_file_path_name("safe.txt", "c" * 32)
        )
        self.assertEqual(filename, "safe.txt")
        self.assertTrue(save_path.endswith("/safe.txt"))


class ChunkUploadMetadataTests(unittest.TestCase):
    def test_traversal_filename_remains_downloadable_after_completion(self):
        asyncio.run(self._run_traversal_upload())

    async def _run_traversal_upload(self):
        original_config = dict(settings.user_config)
        tmpdir = tempfile.TemporaryDirectory()
        try:
            settings.file_storage = "local"
            settings.allowed_file_types = ["*"]
            with patch("core.storage.data_root", Path(tmpdir.name)):
                await Tortoise.init(
                    config={
                        "connections": {
                            "default": {
                                "engine": "tortoise.backends.sqlite",
                                "credentials": {"file_path": ":memory:"},
                            }
                        },
                        "apps": {
                            "models": {
                                "models": ["apps.base.models"],
                                "default_connection": "default",
                            }
                        },
                        "use_tz": False,
                        "timezone": "Asia/Shanghai",
                    }
                )
                await Tortoise.generate_schemas()
                try:
                    raw_name = "../../../../../../filecodebox.db"
                    payload = b"chunk payload"
                    init_result = await views.init_chunk_upload(
                        InitChunkUploadModel(
                            file_name=raw_name,
                            file_size=len(payload),
                            chunk_size=1024,
                            file_hash="f" * 64,
                        )
                    )
                    upload_id = init_result.detail["upload_id"]
                    session = await UploadChunk.get(
                        upload_id=upload_id, chunk_index=-1
                    )
                    self.assertEqual(session.file_name, "filecodebox.db")
                    self.assertNotIn("..", session.save_path)

                    await views.upload_chunk(
                        upload_id=upload_id,
                        chunk_index=0,
                        chunk=UploadFile(
                            file=BytesIO(payload), filename="filecodebox.db"
                        ),
                    )

                    # Simulate a legacy session whose display name was not sanitized.
                    session.file_name = raw_name
                    await session.save(update_fields=["file_name"])

                    complete_result = await views.complete_upload(
                        upload_id=upload_id,
                        data=CompleteUploadModel(
                            expire_value=1, expire_style="day"
                        ),
                        ip="127.0.0.1",
                    )
                    self.assertEqual(complete_result.detail["name"], "filecodebox.db")

                    file_code = await FileCodes.get(code=complete_result.detail["code"])
                    expected_relative_path = session.save_path
                    self.assertEqual(
                        await file_code.get_file_path(), expected_relative_path
                    )
                    storage = views.storages[settings.file_storage]()
                    resolved_path = storage._resolve_safe_path(
                        await file_code.get_file_path()
                    )
                    self.assertEqual(
                        resolved_path, Path(tmpdir.name).resolve() / expected_relative_path
                    )
                    self.assertEqual(resolved_path.read_bytes(), payload)
                finally:
                    await Tortoise.close_connections()
        finally:
            settings.user_config = original_config
            tmpdir.cleanup()


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
