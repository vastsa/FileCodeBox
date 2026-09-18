"""Negative-path coverage for data-integrity and auth boundaries.

Every test here exercises a failure branch, not a happy path:
- download with a count-limited share: second download must be refused
- chunk session cancel/status on a missing upload_id must 404
- an expired presign session must be deleted server-side on access
- admin update_file must enforce code uniqueness and existence
"""
import datetime

import pytest

from core.errors import StorageError
from core.utils import get_select_token, get_now
from tests.conftest import TEST_ADMIN_PASSWORD


def _stored(key: str):
    from core.storage import StoredFile

    return StoredFile(
        file_path=key.rsplit("/", 1)[0], uuid_file_name=key.rsplit("/", 1)[1]
    )


async def _login(client) -> str:
    response = await client.post(
        "/admin/login", json={"password": TEST_ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["token"]


@pytest.mark.asyncio
class TestDownloadCountExhaustion:
    async def test_second_download_refused_after_limit(self, initialized_client):
        share = await initialized_client.post(
            "/share/text",
            data={"text": "one-shot", "expire_value": "1", "expire_style": "count"},
        )
        assert share.status_code == 200
        code = share.json()["detail"]["code"]
        token = await get_select_token(code)

        first = await initialized_client.get(
            "/share/download", params={"key": token, "code": code}
        )
        assert first.status_code == 200

        second = await initialized_client.get(
            "/share/download", params={"key": token, "code": code}
        )
        assert second.json()["code"] == 404


@pytest.mark.asyncio
class TestMissingChunkSession:
    async def test_cancel_missing_session_404(self, initialized_client):
        response = await initialized_client.delete("/chunk/upload/no-such-upload")
        assert response.status_code == 404

    async def test_status_missing_session_404(self, initialized_client):
        response = await initialized_client.get("/chunk/upload/status/no-such-upload")
        assert response.status_code == 404


@pytest.mark.asyncio
class TestExpiredPresignSession:
    async def test_expired_session_is_deleted_and_reports_404(self, initialized_client):
        from apps.base.models import PresignUploadSession

        upload_id = "expiredsession01"
        await PresignUploadSession.create(
            upload_id=upload_id,
            file_name="doc.pdf",
            file_size=10,
            save_path="share/data/2026/01/01/x/doc.pdf",
            mode="proxy",
            expire_value=1,
            expire_style="day",
            expires_at=await get_now() - datetime.timedelta(seconds=1),
        )

        response = await initialized_client.put(
            f"/presign/upload/proxy/{upload_id}",
            files={"file": ("doc.pdf", b"x", "application/pdf")},
        )
        assert response.status_code == 404
        assert await PresignUploadSession.filter(upload_id=upload_id).first() is None


@pytest.mark.asyncio
class TestAdminUpdateFileBoundaries:
    async def _create_file(self, code: str):
        from apps.base.models import FileCodes

        await FileCodes.create(code=code, text="x", size=1, prefix="Text")

    async def test_update_missing_file_404(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.patch(
            "/admin/file/update",
            json={"id": 999999, "prefix": "new"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 404

    async def test_duplicate_code_rejected_400(self, initialized_client):
        await self._create_file("dupcode1")
        await self._create_file("dupcode2")
        token = await _login(initialized_client)

        target = await initialized_client.get(
            "/admin/file/list",
            params={"keyword": "dupcode2"},
            headers={"Authorization": f"Bearer {token}"},
        )
        file_id = target.json()["detail"]["data"][0]["id"]

        response = await initialized_client.patch(
            "/admin/file/update",
            json={"id": file_id, "code": "dupcode1"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 400


@pytest.mark.asyncio
class TestNotFoundHandlerBranches:
    """404 双分支边界：浏览器导航拿主题页（SPA 兜底保留），API 客户端拿 JSON 404。"""

    async def test_api_accept_gets_json_404(self, initialized_client):
        response = await initialized_client.get(
            "/no-such-path", headers={"Accept": "application/json"}
        )
        assert response.status_code == 404
        assert response.json()["code"] == 404
        assert "text/html" not in response.headers["content-type"]

    async def test_browser_accept_gets_theme_page(self, initialized_client):
        response = await initialized_client.get("/no-such-path", headers={"Accept": "text/html"})
        assert response.status_code == 200
        assert "text/html" in response.headers["content-type"]

    async def test_default_star_accept_gets_json_404(self, initialized_client):
        """curl 默认 */* 不含 text/html——必须走 JSON 分支（防误伤脚本调用方）。"""
        response = await initialized_client.get("/no-such-path")
        assert response.status_code == 404
        assert response.json()["code"] == 404


@pytest.mark.asyncio
class TestOneDriveMissingObjectTranslation:
    """OneDrive 缺失对象：graph 的 itemNotFound 必须前置 404，而非外层兜底 503。

    office365 SDK 不在运行时依赖里（Docker 构建不含），用 __new__ 绕过构造、
    假异常类模拟 SDK 边界——只测我们新增的"异常码→StorageError"翻译层。
    """

    def _make_storage(self, monkeypatch, code_value: str):
        import core.storage.onedrive as storage_module
        from core.storage import OneDriveFileStorage

        class FakeClientRequestException(Exception):
            def __init__(self, code: str):
                self.code = code
                super().__init__(code)

        storage = OneDriveFileStorage.__new__(OneDriveFileStorage)
        storage._ClientRequestException = FakeClientRequestException
        storage.proxy = 1

        def fake_to_thread(fn, *args, **kwargs):
            raise FakeClientRequestException(code_value)

        monkeypatch.setattr(storage_module.asyncio, "to_thread", fake_to_thread)
        return storage

    async def test_item_not_found_maps_to_404(self, monkeypatch):
        storage = self._make_storage(monkeypatch, "itemNotFound")
        with pytest.raises(StorageError) as exc_info:
            await storage.get_file_response(_stored("share/data/ghost.bin"))
        assert exc_info.value.status_code == 404

    async def test_other_graph_errors_still_map_to_503(self, monkeypatch):
        storage = self._make_storage(monkeypatch, "accessDenied")
        with pytest.raises(StorageError) as exc_info:
            await storage.get_file_response(_stored("share/data/denied.bin"))
        assert exc_info.value.status_code == 503


@pytest.mark.asyncio
class TestOpenDALMissingObject:
    """OpenDAL 缺失对象经外层兜底已映射 404——用假 operator 钉死该行为，
    防止未来重构破坏（opendal SDK 不在运行时依赖，无法构造真实实例）。"""

    def _make_storage(self, monkeypatch, *, reader_exists: bool):
        import core.storage.opendal as storage_module
        from core.storage import OpenDALFileStorage

        storage = OpenDALFileStorage.__new__(OpenDALFileStorage)

        class FakeStat:
            content_length = 0
            size = 0

        class FakeReader:
            def __init__(self, data: bytes):
                self._data = data

            async def read(self, n: int) -> bytes:
                data, self._data = self._data[:n], self._data[n:]
                return data

        class FakeOperator:
            async def stat(self, path: str):
                if not reader_exists:
                    raise FileNotFoundError(path)
                return FakeStat()

            async def reader(self, path: str):
                if not reader_exists:
                    raise FileNotFoundError(path)
                return FakeReader(b"opendal-payload")

            async def read(self, path: str):
                if not reader_exists:
                    raise FileNotFoundError(path)
                return b"opendal-payload"

        monkeypatch.setattr(storage_module, "logger", storage_module.logger)
        storage.operator = FakeOperator()
        return storage

    async def test_missing_object_maps_to_404(self, monkeypatch):
        storage = self._make_storage(monkeypatch, reader_exists=False)
        with pytest.raises(StorageError) as exc_info:
            await storage.get_file_response(_stored("share/data/ghost.bin"))
        assert exc_info.value.status_code == 404

    async def test_existing_object_streams_payload(self, monkeypatch):
        storage = self._make_storage(monkeypatch, reader_exists=True)
        download = await storage.get_file_response(_stored("share/data/s.bin"))
        chunks = [chunk async for chunk in download.stream_factory()]
        assert b"".join(chunks) == b"opendal-payload"
