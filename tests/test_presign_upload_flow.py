import asyncio
import unittest
from datetime import timedelta
from types import SimpleNamespace

from fastapi import HTTPException

import apps.base.views as views
from apps.base.schemas import PresignUploadInitRequest
from core.settings import settings
from core.utils import get_now


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class FakeUploadLimiter:
    def __init__(self):
        self.added_ips = []

    def add_ip(self, ip):
        self.added_ips.append(ip)


class FakeUploadFile:
    def __init__(self, size):
        self.size = size
        self.filename = "upload.txt"
        self.content_type = "text/plain"


class FakeStorage:
    def __init__(self, presigned_url=None, exists=True):
        self.presigned_url = presigned_url
        self.exists = exists
        self.saved = []
        self.deleted = []

    async def generate_presigned_upload_url(self, save_path, expires_in):
        self.last_presign_request = (save_path, expires_in)
        return self.presigned_url

    async def save_file(self, file, save_path):
        self.saved.append((file, save_path))

    async def file_exists(self, save_path):
        self.last_exists_path = save_path
        return self.exists

    async def delete_file(self, file_code):
        self.deleted.append(file_code)


class FakeSession:
    def __init__(self, mode="direct", file_size=12, expired=False):
        self.upload_id = "upload-1"
        self.file_name = "upload.txt"
        self.file_size = file_size
        self.save_path = "share/data/2026/06/06/upload-1/upload.txt"
        self.mode = mode
        self.expire_value = 2
        self.expire_style = "day"
        self.created_at = None
        self.expires_at = None
        self.expired = expired
        self.deleted = False

    async def is_expired(self):
        return self.expired

    async def delete(self):
        self.deleted = True


class FakeSessionQuery:
    def __init__(self, session):
        self.session = session

    async def first(self):
        return self.session


class FakePresignUploadSession:
    created_payload = None
    session = None

    @classmethod
    async def create(cls, **kwargs):
        cls.created_payload = kwargs
        return SimpleNamespace(**kwargs)

    @classmethod
    def filter(cls, **kwargs):
        cls.filter_kwargs = kwargs
        return FakeSessionQuery(cls.session)


class FakeFileUploadService:
    created_records = []

    @staticmethod
    async def generate_file_path(file_name, upload_id=None):
        filename = file_name.strip()
        return (
            f"share/data/2026/06/06/{upload_id}",
            ".txt",
            "upload",
            filename,
            f"share/data/2026/06/06/{upload_id}/{filename}",
        )

    @classmethod
    async def create_file_record(
        cls, file_name, file_size, file_path, expire_value, expire_style, **extra_fields
    ):
        cls.created_records.append(
            {
                "file_name": file_name,
                "file_size": file_size,
                "file_path": file_path,
                "expire_value": expire_value,
                "expire_style": expire_style,
                **extra_fields,
            }
        )
        return "12345"


class PresignUploadFlowTests(SettingsOverrideMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        self._original_storages = dict(views.storages)
        self._original_session_model = views.PresignUploadSession
        self._original_file_upload_service = views.FileUploadService
        self._original_upload_limiter = views.ip_limit["upload"]
        self.storage = FakeStorage()
        views.storages = {"local": lambda: self.storage}
        views.PresignUploadSession = FakePresignUploadSession
        views.FileUploadService = FakeFileUploadService
        views.ip_limit["upload"] = FakeUploadLimiter()
        FakePresignUploadSession.created_payload = None
        FakePresignUploadSession.session = None
        FakeFileUploadService.created_records = []
        settings.file_storage = "local"
        settings.uploadSize = 1024
        settings.allowed_file_types = ["*"]
        settings.expireStyle = ["day", "hour", "minute", "forever", "count"]

    def tearDown(self):
        views.storages = self._original_storages
        views.PresignUploadSession = self._original_session_model
        views.FileUploadService = self._original_file_upload_service
        views.ip_limit["upload"] = self._original_upload_limiter
        super().tearDown()

    def test_init_returns_proxy_urls_when_storage_has_no_presigned_url(self):
        response = asyncio.run(
            views.presign_upload_init(
                PresignUploadInitRequest(
                    file_name="upload.txt",
                    file_size=12,
                    expire_value=2,
                    expire_style="day",
                ),
                ip="127.0.0.1",
            )
        )

        detail = response.detail
        self.assertEqual(detail["mode"], "proxy")
        self.assertEqual(detail["upload_url"], detail["proxy_upload_url"])
        self.assertEqual(detail["legacy_proxy_upload_url"], f"/api{detail['proxy_upload_url']}")
        self.assertEqual(FakePresignUploadSession.created_payload["file_name"], "upload.txt")
        self.assertEqual(FakePresignUploadSession.created_payload["file_size"], 12)
        self.assertEqual(views.ip_limit["upload"].added_ips, ["127.0.0.1"])

    def test_init_returns_direct_url_when_storage_supports_presigned_upload(self):
        self.storage.presigned_url = "https://storage.example/upload"

        response = asyncio.run(
            views.presign_upload_init(
                PresignUploadInitRequest(file_name="upload.txt", file_size=12),
                ip="127.0.0.1",
            )
        )

        self.assertEqual(response.detail["mode"], "direct")
        self.assertEqual(response.detail["upload_url"], "https://storage.example/upload")
        self.assertNotIn("proxy_upload_url", response.detail)

    def test_init_rejects_disallowed_expiration_style(self):
        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                views.presign_upload_init(
                    PresignUploadInitRequest(
                        file_name="upload.txt",
                        file_size=12,
                        expire_style="week",
                    ),
                    ip="127.0.0.1",
                )
            )

        self.assertEqual(error.exception.status_code, 400)

    def test_confirm_requires_uploaded_direct_file_before_creating_record(self):
        FakePresignUploadSession.session = FakeSession(mode="direct")
        self.storage.exists = True

        response = asyncio.run(views.presign_upload_confirm("upload-1", ip="127.0.0.1"))

        self.assertEqual(response.detail, {"code": "12345", "name": "upload.txt"})
        self.assertTrue(FakePresignUploadSession.session.deleted)
        self.assertEqual(FakeFileUploadService.created_records[0]["file_size"], 12)
        self.assertEqual(
            FakeFileUploadService.created_records[0]["file_path"],
            "share/data/2026/06/06/upload-1",
        )

    def test_confirm_rejects_missing_uploaded_direct_file(self):
        FakePresignUploadSession.session = FakeSession(mode="direct")
        self.storage.exists = False

        with self.assertRaises(HTTPException) as error:
            asyncio.run(views.presign_upload_confirm("upload-1", ip="127.0.0.1"))

        self.assertEqual(error.exception.status_code, 404)
        self.assertFalse(FakePresignUploadSession.session.deleted)
        self.assertEqual(FakeFileUploadService.created_records, [])

    def test_proxy_upload_rejects_size_mismatch_before_saving_file(self):
        FakePresignUploadSession.session = FakeSession(mode="proxy", file_size=10)

        with self.assertRaises(HTTPException) as error:
            asyncio.run(
                views.presign_upload_proxy(
                    "upload-1",
                    file=FakeUploadFile(size=2048),
                    ip="127.0.0.1",
                )
            )

        self.assertEqual(error.exception.status_code, 403)
        self.assertEqual(self.storage.saved, [])

    def test_cancel_direct_session_removes_uploaded_object_when_present(self):
        FakePresignUploadSession.session = FakeSession(mode="direct")
        self.storage.exists = True

        response = asyncio.run(views.presign_upload_cancel("upload-1"))

        self.assertEqual(response.detail, {"message": "上传会话已取消"})
        self.assertTrue(FakePresignUploadSession.session.deleted)
        self.assertEqual(len(self.storage.deleted), 1)
        self.assertEqual(self.storage.deleted[0].file_path, "share/data/2026/06/06/upload-1")
        self.assertEqual(self.storage.deleted[0].uuid_file_name, "upload.txt")

    def test_expired_session_is_deleted_and_rejected(self):
        FakePresignUploadSession.session = FakeSession(mode="direct", expired=True)
        FakePresignUploadSession.session.expires_at = asyncio.run(get_now()) - timedelta(seconds=1)

        with self.assertRaises(HTTPException) as error:
            asyncio.run(views.presign_upload_confirm("upload-1", ip="127.0.0.1"))

        self.assertEqual(error.exception.status_code, 404)
        self.assertTrue(FakePresignUploadSession.session.deleted)
