"""Negative-path coverage for data-integrity and auth boundaries.

Every test here exercises a failure branch, not a happy path:
- download with a count-limited share: second download must be refused
- chunk session cancel/status on a missing upload_id must 404
- an expired presign session must be deleted server-side on access
- admin update_file must enforce code uniqueness and existence
"""
import datetime

import pytest

from core.utils import get_select_token, get_now
from tests.conftest import TEST_ADMIN_PASSWORD


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
