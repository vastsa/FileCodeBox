"""S3 storage backend coverage via moto (in-memory S3).

The largest remaining test blind spot (the whole backend had only stub-level
tests). Focus on failure branches: missing objects, chunk merge failures,
cleanup scoping, presign behavior. Exercises the real settings → S3FileStorage
config surface.
"""
import hashlib
import io
from types import SimpleNamespace

import pytest
from core.errors import StorageError
from core.storage import S3FileStorage, StoredFile

S3_SETTINGS = {
    "file_storage": "s3",
    "s3_bucket_name": "drill-bucket",
    "s3_access_key_id": "testing",
    "s3_secret_access_key": "testing",
    "s3_hostname": "minio.local",
    "s3_region_name": "us-east-1",
    "s3_endpoint_url": "",
    "jwt_secret": "drill" * 12,
    "s3_signature_version": "s3v4",
}


@pytest.fixture
async def s3_storage():
    """Real in-process moto HTTP server (mock_aws cannot intercept aioboto3's
    aiohttp stack) + S3 config override + bucket creation."""
    from core.settings import settings
    from moto.server import ThreadedMotoServer

    server = ThreadedMotoServer("127.0.0.1", 0)
    server.start()
    endpoint = f"http://127.0.0.1:{server._server.server_port}"
    original = dict(settings.user_config)
    settings.user_config = {**original, **S3_SETTINGS, "s3_endpoint_url": endpoint}
    try:
        session = __import__("aioboto3").Session(
            aws_access_key_id="testing", aws_secret_access_key="testing"
        )
        async with session.client("s3", endpoint_url=endpoint, region_name="us-east-1") as s3:
            await s3.create_bucket(Bucket="drill-bucket")
        yield S3FileStorage()
    finally:
        settings.user_config = original
        server.stop()


def _stored(key: str) -> StoredFile:
    return StoredFile(
        file_path=key.rsplit("/", 1)[0], uuid_file_name=key.rsplit("/", 1)[1]
    )


def _records(chunks: dict[int, bytes]) -> dict:
    return {
        i: SimpleNamespace(chunk_hash=hashlib.sha256(d).hexdigest())
        for i, d in chunks.items()
    }


async def _seed_chunks(s3_storage, upload_id, save_path, chunks: dict[int, bytes]):
    for index, data in chunks.items():
        await s3_storage.save_chunk(upload_id, index, data, "ignored", save_path)


@pytest.mark.asyncio
class TestS3ObjectBasics:
    async def test_save_and_exists_roundtrip(self, s3_storage):
        await s3_storage.save_file(
            io.BytesIO(b"payload"), "share/data/f.bin", "application/octet-stream"
        )
        assert await s3_storage.file_exists("share/data/f.bin") is True
        assert await s3_storage.file_exists("share/data/missing.bin") is False

    async def test_delete_file_removes_object(self, s3_storage):
        await s3_storage.save_file(io.BytesIO(b"payload"), "share/data/f.bin")
        await s3_storage.delete_file(_stored("share/data/f.bin"))
        assert await s3_storage.file_exists("share/data/f.bin") is False

    async def test_presigned_upload_url_targets_bucket_and_key(self, s3_storage):
        url = await s3_storage.generate_presigned_upload_url("share/data/f.bin", 900)
        assert "drill-bucket" in url
        assert "f.bin" in url
        assert "X-Amz-Signature" in url

    async def test_get_file_url_proxy_uses_local_dispatch(self, s3_storage):
        """proxy 模式必须走本地 /share/download 分发（取件计数/前置 404 生效）。"""
        from core.settings import settings

        settings.user_config = {**settings.user_config, "s3_proxy": 1}
        proxied_storage = S3FileStorage()
        file_code = StoredFile(
            file_path="share/data", uuid_file_name="f.bin", code="abcd1"
        )
        proxied = await proxied_storage.get_file_url(file_code)
        assert proxied.startswith("/share/download?")

    async def test_get_file_url_direct_returns_presigned(self, s3_storage):
        file_code = StoredFile(
            file_path="share/data", uuid_file_name="f.bin", code="abcd1"
        )
        direct = await s3_storage.get_file_url(file_code)
        assert direct.startswith("http") and "drill-bucket" in direct


@pytest.mark.asyncio
class TestS3GetFileResponse:
    async def test_missing_object_raises_404_upfront(self, s3_storage):
        """缺失对象必须前置 404，而不是签发 200 的坏流（与 local 后端语义对齐）。"""
        with pytest.raises(StorageError) as exc_info:
            await s3_storage.get_file_response(_stored("share/data/ghost.bin"))
        assert exc_info.value.status_code == 404

    async def test_existing_object_returns_download_with_length(self, s3_storage):
        await s3_storage.save_file(io.BytesIO(b"payload"), "share/data/f.bin")
        download = await s3_storage.get_file_response(_stored("share/data/f.bin"))
        assert download.headers["Content-Length"] == "7"
        assert download.headers["Content-Disposition"].startswith("attachment;")

    async def test_stream_factory_roundtrip_via_presigned_url(self, s3_storage):
        """流式生成器经 presigned URL 真实往返 moto 服务，内容一致。"""
        payload = b"stream-roundtrip-payload"
        await s3_storage.save_file(io.BytesIO(payload), "share/data/s.bin")
        download = await s3_storage.get_file_response(_stored("share/data/s.bin"))
        chunks = [chunk async for chunk in download.stream_factory()]
        assert b"".join(chunks) == payload


@pytest.mark.asyncio
class TestS3ChunkMerge:
    async def test_merge_success_roundtrip_then_cleanup(self, s3_storage):
        upload_id = "up01"
        save_path = "share/data/2026/01/01/up01/merged.bin"
        parts = {0: b"AAAA", 1: b"BBBB"}
        await _seed_chunks(s3_storage, upload_id, save_path, parts)
        _, file_hash = await s3_storage.merge_chunks(
            upload_id, 2, 4, save_path, _records(parts)
        )
        assert file_hash == hashlib.sha256(b"AAAABBBB").hexdigest()

        async with s3_storage._client() as s3:
            resp = await s3.get_object(Bucket="drill-bucket", Key=save_path)
            merged = await resp["Body"].read()
        assert merged == b"AAAABBBB"

        await s3_storage.clean_chunks(upload_id, save_path)
        assert (
            await s3_storage.file_exists(
                f"share/data/2026/01/01/up01/chunks/{upload_id}/0.part"
            )
            is False
        )

    async def test_merge_missing_chunk_aborts_and_raises(self, s3_storage):
        upload_id = "up02"
        save_path = "share/data/2026/01/01/up02/merged.bin"
        await _seed_chunks(s3_storage, upload_id, save_path, {1: b"BBBB"})  # 缺分片 0
        with pytest.raises(ValueError, match="分片0"):
            await s3_storage.merge_chunks(
                upload_id, 2, 4, save_path, _records({0: b"AAAA", 1: b"BBBB"})
            )
        # abort 后不得留下半成品对象
        assert await s3_storage.file_exists(save_path) is False

    async def test_merge_hash_mismatch_aborts_and_raises(self, s3_storage):
        upload_id = "up03"
        save_path = "share/data/2026/01/01/up03/merged.bin"
        await _seed_chunks(s3_storage, upload_id, save_path, {0: b"AAAA"})
        bad_records = {0: SimpleNamespace(chunk_hash="f" * 64)}  # 与实际不符
        with pytest.raises(ValueError, match="哈希不匹配"):
            await s3_storage.merge_chunks(upload_id, 1, 4, save_path, bad_records)
        assert await s3_storage.file_exists(save_path) is False

    async def test_clean_chunks_scoped_to_upload_only(self, s3_storage):
        # 注意 chunk 目录派生自 save_path 的父目录——两个 upload 必须各自 save_path
        save_a = "share/data/2026/01/01/upa/merged.bin"
        save_b = "share/data/2026/01/01/upb/merged.bin"
        await _seed_chunks(s3_storage, "upa", save_a, {0: b"AA"})
        await _seed_chunks(s3_storage, "upb", save_b, {0: b"BB"})
        await s3_storage.clean_chunks("upa", save_a)
        assert (
            await s3_storage.file_exists("share/data/2026/01/01/upa/chunks/upa/0.part")
            is False
        )
        assert (
            await s3_storage.file_exists("share/data/2026/01/01/upb/chunks/upb/0.part")
            is True
        )

    async def test_save_chunk_stores_declared_hash_metadata(self, s3_storage):
        await s3_storage.save_chunk("upm", 0, b"DATA", "cafe" * 16, "share/data/x/m.bin")
        async with s3_storage._client() as s3:
            head = await s3.head_object(
                Bucket="drill-bucket", Key="share/data/x/chunks/upm/0.part"
            )
        assert head["Metadata"]["chunk-hash"] == "cafe" * 16
