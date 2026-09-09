"""End-to-end tests for the presigned-upload flow over the real ASGI stack.

With the local storage backend ``generate_presigned_upload_url`` returns None,
so sessions take proxy mode: init -> PUT proxy -> confirm -> select/download,
plus status/cancel bookkeeping.
"""
import io

import pytest

from apps.base.models import PresignUploadSession
from tests.test_integration_journey import _download, _select


@pytest.mark.usefixtures("initialized_client")
class TestPresignProxyJourney:
    async def _init(self, client, size=1024, name="presign.bin"):
        response = await client.post(
            "/presign/upload/init",
            json={
                "file_name": name,
                "file_size": size,
                "expire_value": 1,
                "expire_style": "day",
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["detail"]

    async def test_proxy_upload_auto_confirms_and_downloads(self, client):
        payload = bytes(range(256)) * 4
        init = await self._init(client, size=len(payload))
        assert init["mode"] == "proxy", "local backend must fall back to proxy mode"
        assert init["upload_url"].endswith(f"/presign/upload/proxy/{init['upload_id']}")

        # Proxy PUT stores the file, creates the share record, and consumes the
        # session in one step (the confirm endpoint is for S3 direct mode only).
        response = await client.put(
            init["upload_url"],
            files={"file": ("presign.bin", io.BytesIO(payload), "application/octet-stream")},
        )
        assert response.status_code == 200, response.text
        code = response.json()["detail"]["code"]

        detail = (await _select(client, code))["detail"]
        downloaded = await _download(client, detail["download_url"])
        assert downloaded.content == payload

        assert not await PresignUploadSession.filter(
            upload_id=init["upload_id"]
        ).exists()

    async def test_status_reports_session(self, client):
        init = await self._init(client, size=64)
        response = await client.get(f"/presign/upload/status/{init['upload_id']}")
        assert response.status_code == 200, response.text
        detail = response.json()["detail"]
        assert detail["upload_id"] == init["upload_id"]
        assert detail["mode"] == "proxy"
        assert detail["is_expired"] is False

    async def test_confirm_rejects_proxy_mode_sessions(self, client):
        # The confirm endpoint is only meaningful for S3 direct mode; a proxy
        # session must be rejected with a clear error instead of confirming.
        init = await self._init(client, size=64)
        response = await client.post(f"/presign/upload/confirm/{init['upload_id']}")
        assert response.status_code == 400, response.text

    async def test_cancel_releases_session(self, client):
        init = await self._init(client, size=64)
        response = await client.delete(f"/presign/upload/{init['upload_id']}")
        assert response.status_code == 200, response.text
        assert not await PresignUploadSession.filter(
            upload_id=init["upload_id"]
        ).exists()

    async def test_size_limit_enforced_at_init(self, client):
        from apps.base.models import KeyValue
        from core.settings import settings

        record = await KeyValue.filter(key="settings").first()
        config = dict(record.value or {})
        config["upload_size"] = 1024
        record.value = config
        await record.save()
        settings.user_config = config

        response = await client.post(
            "/presign/upload/init",
            json={
                "file_name": "huge.bin",
                "file_size": 4096,
                "expire_value": 1,
                "expire_style": "day",
            },
        )
        assert response.status_code == 403, response.text
