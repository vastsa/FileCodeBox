"""OSS compatibility regressions: real SDK request preparation, no external I/O."""
from datetime import timedelta
from unittest.mock import AsyncMock
from urllib.parse import urlsplit

import aioboto3
import pytest
from botocore.exceptions import ClientError
from fastapi import HTTPException

from apps.base import services, tasks, views
from apps.base.models import FileCodes, StorageReservation, UploadChunk
from core.settings import settings
from core.storage.s3 import S3FileStorage
from core.utils import get_now


@pytest.fixture
def storage(monkeypatch):
    monkeypatch.setattr(settings, "user_config", {
        **settings.user_config, "file_storage": "s3", "upload_size": 1024,
        "chunk_expire_hours": 24,
    })
    storage = S3FileStorage.__new__(S3FileStorage)
    storage.signature_version = "s3v4"
    storage.addressing_style = "virtual"
    storage.bucket_name = "test-bucket"
    # Reserved .invalid domain; before-send hooks stop requests before any I/O.
    storage.endpoint_url = "https://oss-cn-hangzhou.example.invalid"
    storage.region_name = "oss-cn-hangzhou"
    storage.aws_session_token = None
    storage.session = aioboto3.Session(
        aws_access_key_id="testing", aws_secret_access_key="testing"
    )
    return storage


def test_checksum_config_preserves_signature_and_addressing(storage):
    config = storage._client_config()
    assert config.request_checksum_calculation == "when_required"
    assert config.response_checksum_validation == "when_required"
    assert config.signature_version == "s3v4"
    assert config.s3["addressing_style"] == "virtual"


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", ["PutObject", "UploadPart"])
async def test_sdk_upload_has_no_flexible_checksum_trailer(storage, monkeypatch, operation):
    monkeypatch.setenv("AWS_REQUEST_CHECKSUM_CALCULATION", "when_supported")
    monkeypatch.setenv("AWS_RESPONSE_CHECKSUM_VALIDATION", "when_supported")
    captured = []

    class RequestCaptured(Exception):
        pass

    def intercept(request, **kwargs):
        captured.append(request)
        raise RequestCaptured

    # Register on the session so save_chunk's real _client() inherits the hook.
    storage.session.events.register(f"before-send.s3.{operation}", intercept)
    with pytest.raises(RequestCaptured):
        if operation == "PutObject":
            await storage.save_chunk("up", 0, b"payload", "hash", "share/file.bin")
        else:
            async with storage._client() as client:
                assert client.meta.config.response_checksum_validation == "when_required"
                await client.upload_part(
                    Bucket=storage.bucket_name, Key="share/file.bin", UploadId="up",
                    PartNumber=1, Body=b"payload",
                )
    assert len(captured) == 1
    request = captured[0]
    headers = {key.lower(): value for key, value in request.headers.items()}
    assert "x-amz-trailer" not in headers
    assert not any(key.startswith("x-amz-checksum-") for key in headers)
    assert "x-amz-sdk-checksum-algorithm" not in headers
    assert b"aws-chunked" not in headers.get("content-encoding", b"")
    assert b"TRAILER" not in headers.get("x-amz-content-sha256", b"")
    assert urlsplit(request.url).hostname == "test-bucket.oss-cn-hangzhou.example.invalid"
    assert not urlsplit(request.url).path.startswith("/test-bucket/")


class FakeS3:
    """Only single-object deletion is available; paginate from a bounded snapshot."""

    def __init__(self, keys=(), fail_key=None, list_error=False):
        self.keys = set(keys)
        self.fail_key = fail_key
        self.list_error = list_error
        self.deleted = []
        self.prefixes = []
        self.pages = 0

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass

    def get_paginator(self, operation):
        assert operation == "list_objects_v2"
        return self

    async def paginate(self, Bucket, Prefix):
        assert Bucket == "test-bucket"
        self.prefixes.append(Prefix)
        if self.list_error:
            raise RuntimeError("list failed")
        # Also exercise a page without Contents.
        yield {}
        keys = sorted(key for key in self.keys if key.startswith(Prefix))
        for offset in range(0, len(keys), 1000):
            self.pages += 1
            yield {"Contents": [{"Key": key} for key in keys[offset:offset + 1000]]}

    async def delete_object(self, Bucket, Key):
        assert Bucket == "test-bucket"
        if Key == self.fail_key:
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "DeleteObject")
        self.deleted.append(Key)
        self.keys.discard(Key)
        return {}


def install_client(storage, monkeypatch, fake):
    monkeypatch.setattr(storage, "_client", lambda: fake)
    monkeypatch.setattr(tasks, "storages", {"s3": lambda: storage})
    monkeypatch.setattr(views, "storages", {"s3": lambda: storage})
    monkeypatch.setattr(services.FileUploadService, "_storage", lambda: storage)


@pytest.mark.asyncio
async def test_cleanup_paginates_and_keeps_neighboring_upload(storage, monkeypatch):
    prefix = "share/chunks/up/"
    keys = {f"{prefix}{i}.part" for i in range(1005)}
    neighbors = {"share/chunks/up-other/0.part", "share/file.bin"}
    fake = FakeS3(keys | neighbors)
    install_client(storage, monkeypatch, fake)
    await storage.clean_chunks("up", "share/file.bin")
    assert fake.prefixes == [prefix]
    assert fake.pages == 2
    assert set(fake.deleted) == keys
    assert fake.keys == neighbors
    await storage.clean_chunks("up", "share/file.bin")  # Empty/idempotent retry.
    assert fake.keys == neighbors


@pytest.mark.asyncio
async def test_cleanup_listing_failure_propagates(storage, monkeypatch):
    install_client(storage, monkeypatch, FakeS3(list_error=True))
    with pytest.raises(RuntimeError, match="list failed"):
        await storage.clean_chunks("up", "share/file.bin")


async def seed_session(upload_id="up"):
    now = await get_now()
    values = dict(
        upload_id=upload_id, chunk_hash="a" * 64, total_chunks=2,
        file_size=8, chunk_size=4, file_name="file.bin", save_path="share/file.bin",
        created_at=now - timedelta(hours=48),
    )
    session = await UploadChunk.create(chunk_index=-1, **values)
    for index in range(2):
        await UploadChunk.create(chunk_index=index, completed=True, **values)
    await StorageReservation.create(
        token=f"chunk:{upload_id}", size=8, expires_at=now + timedelta(hours=1)
    )
    return session


async def run_cleanup_round(monkeypatch):
    class StopLoop(Exception):
        pass

    monkeypatch.setattr(tasks, "refresh_settings", AsyncMock())
    monkeypatch.setattr(tasks.asyncio, "sleep", AsyncMock(side_effect=StopLoop))
    with pytest.raises(StopLoop):
        await tasks.clean_incomplete_uploads()


@pytest.mark.asyncio
async def test_partial_failure_keeps_records_then_task_retries(db, storage, monkeypatch):
    await seed_session()
    await seed_session("other")
    keys = {"share/chunks/up/0.part", "share/chunks/up/1.part"}
    fake = FakeS3(keys, fail_key="share/chunks/up/1.part")
    install_client(storage, monkeypatch, fake)
    with pytest.raises(ClientError):
        await storage.clean_chunks("up", "share/file.bin")
    assert fake.keys == {fake.fail_key}
    await run_cleanup_round(monkeypatch)
    assert await UploadChunk.filter(upload_id="up").count() == 3
    assert await StorageReservation.filter(token="chunk:up").exists()
    # Failure in one session must not prevent another session being cleaned.
    assert not await UploadChunk.filter(upload_id="other").exists()
    fake.fail_key = None
    await run_cleanup_round(monkeypatch)
    assert not fake.keys
    assert not await UploadChunk.filter(upload_id="up").exists()
    assert not await StorageReservation.filter(token="chunk:up").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("cleanup_fails", [False, True])
async def test_completed_share_survives_cleanup_failure(db, storage, monkeypatch, cleanup_fails):
    session = await seed_session()
    fake = FakeS3(list_error=cleanup_fails)
    install_client(storage, monkeypatch, fake)
    monkeypatch.setattr(storage, "merge_chunks", AsyncMock(return_value=("share/file.bin", "a" * 64)))
    monkeypatch.setattr(services, "reserve_storage", AsyncMock())
    monkeypatch.setattr(services, "get_expire_info", AsyncMock(return_value=(
        await get_now() + timedelta(days=1), -1, 0, "oss-code",
    )))
    result = await services.FileUploadService.complete_chunked_upload("up", session, 1, "day")
    assert result == {"code": "oss-code", "name": "file.bin"}
    assert await FileCodes.filter(code="oss-code").exists()
    assert await UploadChunk.filter(upload_id="up").exists() is cleanup_fails
    assert not await StorageReservation.filter(token="chunk:up").exists()
    if cleanup_fails:
        fake.list_error = False
        await run_cleanup_round(monkeypatch)
        assert not await UploadChunk.filter(upload_id="up").exists()
        assert await FileCodes.filter(code="oss-code").exists()


@pytest.mark.asyncio
async def test_oversize_cleanup_failure_keeps_retry_records(db, storage, monkeypatch):
    session = await seed_session()
    install_client(storage, monkeypatch, FakeS3(list_error=True))
    monkeypatch.setattr(services, "reserve_storage", AsyncMock())
    settings.user_config = {**settings.user_config, "upload_size": 1}
    with pytest.raises(HTTPException) as error:
        await services.FileUploadService.complete_chunked_upload("up", session, 1, "day")
    assert error.value.status_code == 403
    assert await UploadChunk.filter(upload_id="up").count() == 3
    assert not await FileCodes.all().exists()


@pytest.mark.asyncio
async def test_cancel_cleanup_failure_keeps_retry_records(db, storage, monkeypatch):
    await seed_session()
    fake = FakeS3(list_error=True)
    install_client(storage, monkeypatch, fake)
    with pytest.raises(HTTPException) as error:
        await views.cancel_upload("up")
    assert error.value.status_code == 503
    assert await UploadChunk.filter(upload_id="up").count() == 3
    assert await StorageReservation.filter(token="chunk:up").exists()
    fake.list_error = False
    await views.cancel_upload("up")
    assert not await UploadChunk.filter(upload_id="up").exists()
    assert not await StorageReservation.filter(token="chunk:up").exists()


@pytest.mark.asyncio
@pytest.mark.parametrize("delete_share", [False, True])
async def test_published_session_cannot_be_reused(db, storage, monkeypatch, delete_share):
    session = await seed_session()
    install_client(storage, monkeypatch, FakeS3(list_error=True))
    merge = AsyncMock(return_value=("share/file.bin", "a" * 64))
    save_chunk = AsyncMock()
    reserve = AsyncMock()
    monkeypatch.setattr(storage, "merge_chunks", merge)
    monkeypatch.setattr(storage, "save_chunk", save_chunk)
    monkeypatch.setattr(services, "reserve_storage", reserve)
    monkeypatch.setattr(views, "reserve_storage", reserve)
    monkeypatch.setattr(services, "get_expire_info", AsyncMock(return_value=(
        await get_now() + timedelta(days=1), -1, 0, "oss-code",
    )))
    result = await services.FileUploadService.complete_chunked_upload("up", session, 1, "day")
    assert result["code"] == "oss-code"
    persisted_session = await UploadChunk.get(upload_id="up", chunk_index=-1)
    assert persisted_session.completed is True
    assert await FileCodes.filter(upload_id="up").count() == 1
    if delete_share:
        # The terminal marker must survive expiration/deletion of the share itself.
        await FileCodes.filter(upload_id="up").delete()

    with pytest.raises(HTTPException) as error:
        await services.FileUploadService.complete_chunked_upload(
            "up", persisted_session, 1, "day"
        )
    assert error.value.status_code == 409
    with pytest.raises(HTTPException) as error:
        await views.complete_upload(
            "up", views.CompleteUploadModel(expire_value=1, expire_style="day"), "127.0.0.1"
        )
    assert error.value.status_code == 409

    # Even when a cleaned fragment no longer has a row, it cannot be uploaded again.
    await UploadChunk.filter(upload_id="up", chunk_index=0).delete()
    chunk = AsyncMock()
    with pytest.raises(HTTPException) as error:
        await views.upload_chunk("up", 0, chunk)
    assert error.value.status_code == 409
    chunk.read.assert_not_awaited()
    save_chunk.assert_not_awaited()
    merge.assert_awaited_once()
    reserve.assert_awaited_once()
    assert await FileCodes.filter(upload_id="up").count() == (0 if delete_share else 1)

    # The -1 cleanup marker is not a file fragment or progress credit.
    status = await views.get_upload_status("up")
    assert status.detail["uploaded_chunks"] == [1]
    assert status.detail["progress"] == 50

    # Initializing the same file must create a new upload, not revive the old ID.
    initialized = await views.init_chunk_upload(views.InitChunkUploadModel(
        file_name="file.bin", file_size=8, chunk_size=4, file_hash="a" * 64,
    ))
    assert initialized.detail["upload_id"] != "up"
    assert initialized.detail["uploaded_chunks"] == []
    assert (await UploadChunk.get(upload_id="up", chunk_index=-1)).completed is True
