"""WebDAV storage backend coverage against a real in-process WebDAV server.

aioboto3-style mocking cannot fake aiohttp; the backend speaks real HTTP
(HEAD/GET/PUT/DELETE/MKCOL/PROPFIND), so the fixture boots a minimal WebDAV
server over a temp directory and exercises the backend through the wire.
Focus on failure branches: missing objects, merge failures, cleanup scoping,
connection errors.
"""
import hashlib
import io
import shutil
import tempfile
from pathlib import Path
from types import SimpleNamespace

import pytest
from aiohttp import web

from core.errors import StorageError
from core.storage import StoredFile, WebDAVFileStorage


def make_dav_app(root: Path) -> web.Application:
    """Minimal WebDAV server: HEAD/GET/PUT/DELETE/MKCOL/PROPFIND over `root`."""

    def _fs_path(request: web.Request) -> Path | None:
        rel = request.match_info.get("path", "")
        target = (root / rel).resolve()
        if not str(target).startswith(str(root)):
            return None
        return target

    async def handler(request: web.Request) -> web.StreamResponse:
        target = _fs_path(request)
        if target is None:
            return web.Response(status=403)
        method = request.method

        if method == "HEAD":
            if target.is_file():
                return web.Response(
                    status=200, headers={"Content-Length": str(target.stat().st_size)}
                )
            if target.is_dir():
                return web.Response(status=200)
            return web.Response(status=404)

        if method == "GET":
            if target.is_file():
                return web.FileResponse(target)
            return web.Response(status=404)

        if method == "PUT":
            if target.is_dir():
                return web.Response(status=409)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(await request.read())
            return web.Response(status=201)

        if method == "MKCOL":
            if target.exists():
                return web.Response(status=405)
            if not target.parent.exists():
                return web.Response(status=409)
            target.mkdir()
            return web.Response(status=201)

        if method == "DELETE":
            if target.is_file():
                target.unlink()
                return web.Response(status=204)
            if target.is_dir():
                shutil.rmtree(target)
                return web.Response(status=204)
            return web.Response(status=404)

        if method == "PROPFIND":
            if not target.exists() or not target.is_dir():
                return web.Response(status=404)
            hrefs = [p.relative_to(root).as_posix() for p in target.iterdir()]
            body = "".join(
                f"<D:response><D:href>{h}</D:href></D:response>" for h in hrefs
            )
            xml = f"<D:multistatus>{body}</D:multistatus>"
            return web.Response(status=207, text=xml, content_type="application/xml")

        return web.Response(status=405)

    app = web.Application()
    app.router.add_route("*", "/{path:.*}", handler)
    return app


@pytest.fixture
async def dav_storage():
    from core.settings import settings
    from aiohttp.test_utils import TestServer

    root = Path(tempfile.mkdtemp(prefix="fcb-dav-"))
    app = make_dav_app(root)
    server = TestServer(app)
    await server.start_server()
    endpoint = f"http://127.0.0.1:{server.port}/dav/"

    original = dict(settings.user_config)
    settings.user_config = {
        **original,
        "file_storage": "webdav",
        "webdav_url": endpoint,
        "webdav_username": "user",
        "webdav_password": "pass",
    }
    try:
        yield WebDAVFileStorage(), root
    finally:
        settings.user_config = original
        await server.close()
        shutil.rmtree(root, ignore_errors=True)


def _stored(key: str) -> StoredFile:
    return StoredFile(
        file_path=key.rsplit("/", 1)[0], uuid_file_name=key.rsplit("/", 1)[1]
    )


def _records(chunks: dict[int, bytes]) -> dict:
    return {
        i: SimpleNamespace(chunk_hash=hashlib.sha256(d).hexdigest())
        for i, d in chunks.items()
    }


@pytest.mark.asyncio
class TestWebDAVObjectBasics:
    async def test_save_roundtrip_and_exists(self, dav_storage):
        storage, _ = dav_storage
        await storage.save_file(
            io.BytesIO(b"payload"), "share/data/f.bin", "application/octet-stream"
        )
        assert await storage.file_exists("share/data/f.bin") is True
        assert await storage.file_exists("share/data/ghost.bin") is False

    async def test_delete_file_and_empty_parent_dirs(self, dav_storage):
        storage, _ = dav_storage
        await storage.save_file(io.BytesIO(b"payload"), "share/data/2026/01/01/x/f.bin")
        await storage.delete_file(_stored("share/data/2026/01/01/x/f.bin"))
        assert await storage.file_exists("share/data/2026/01/01/x/f.bin") is False
        # 空父目录被逐级清理（file_exists 对目录 HEAD 也是 404）
        assert await storage.file_exists("share/data/2026/01/01/x") is False

    async def test_delete_missing_file_is_accepted(self, dav_storage):
        storage, _ = dav_storage
        await storage.delete_file(_stored("share/data/never-existed.bin"))

    async def test_get_file_response_roundtrip(self, dav_storage):
        storage, _ = dav_storage
        payload = b"dav-stream-payload"
        await storage.save_file(io.BytesIO(payload), "share/data/s.bin")
        download = await storage.get_file_response(_stored("share/data/s.bin"))
        assert download.headers["Content-Length"] == str(len(payload))
        chunks = [chunk async for chunk in download.stream_factory()]
        assert b"".join(chunks) == payload


@pytest.mark.asyncio
class TestWebDAVGetFileResponseFailures:
    async def test_missing_object_raises_404_upfront(self, dav_storage):
        """缺失对象前置 404，与 local/S3 语义对齐（不许 200 坏流）。"""
        storage, _ = dav_storage
        with pytest.raises(StorageError) as exc_info:
            await storage.get_file_response(_stored("share/data/ghost.bin"))
        assert exc_info.value.status_code == 404

    async def test_connection_error_maps_to_503(self, monkeypatch):
        from core.settings import settings

        original = dict(settings.user_config)
        settings.user_config = {
            **original,
            "webdav_url": "http://127.0.0.1:1/",  # 无服务的端口
            "webdav_username": "u",
            "webdav_password": "p",
        }
        try:
            storage = WebDAVFileStorage()
            with pytest.raises(StorageError) as exc_info:
                await storage.get_file_response(_stored("share/data/x.bin"))
            assert exc_info.value.status_code == 503
        finally:
            settings.user_config = original


@pytest.mark.asyncio
class TestWebDAVChunkMerge:
    async def test_merge_success_and_cleanup(self, dav_storage):
        storage, _ = dav_storage
        upload_id = "up01"
        save_path = "share/data/2026/01/01/up01/merged.bin"
        parts = {0: b"AAAA", 1: b"BBBB"}
        for i, data in parts.items():
            await storage.save_chunk(upload_id, i, data, "ignored", save_path)
        _, file_hash = await storage.merge_chunks(
            upload_id, 2, 4, save_path, _records(parts)
        )
        assert file_hash == hashlib.sha256(b"AAAABBBB").hexdigest()
        assert await storage.file_exists(save_path) is True

        await storage.clean_chunks(upload_id, save_path)
        assert (
            await storage.file_exists(
                f"share/data/2026/01/01/up01/chunks/{upload_id}/0.part"
            )
            is False
        )

    async def test_merge_missing_chunk_raises(self, dav_storage):
        storage, _ = dav_storage
        save_path = "share/data/2026/01/01/up02/merged.bin"
        await storage.save_chunk("up02", 1, b"BBBB", "ignored", save_path)  # 缺分片 0
        with pytest.raises(ValueError, match="分片0"):
            await storage.merge_chunks(
                "up02", 2, 4, save_path, _records({0: b"AAAA", 1: b"BBBB"})
            )
        assert await storage.file_exists(save_path) is False

    async def test_merge_hash_mismatch_raises(self, dav_storage):
        storage, _ = dav_storage
        save_path = "share/data/2026/01/01/up03/merged.bin"
        await storage.save_chunk("up03", 0, b"AAAA", "ignored", save_path)
        bad = {0: SimpleNamespace(chunk_hash="f" * 64)}
        with pytest.raises(ValueError, match="哈希不匹配"):
            await storage.merge_chunks("up03", 1, 4, save_path, bad)
        assert await storage.file_exists(save_path) is False
