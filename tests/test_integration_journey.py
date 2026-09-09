"""End-to-end integration tests over the real ASGI stack (httpx).

Covers the core user journey that legacy unittest tests skip by calling view
functions directly: routing, auth dependencies, rate-limit middleware, and
storage I/O in one chain.

Route note: /share and /chunk routes are registered with trailing slashes and
rely on redirect_slashes for the bare form; tests use the canonical slash form.
"""
import io

import httpx
import pytest

from apps.base.models import KeyValue
from core.settings import settings
from tests.conftest import TEST_ADMIN_PASSWORD


async def _login(client: httpx.AsyncClient) -> str:
    response = await client.post(
        "/admin/login",
        json={"username": "admin", "password": TEST_ADMIN_PASSWORD},
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["token"]


async def _set_db_config(key: str, value):
    """Persist a config change into the settings KeyValue row.

    The per-request middleware refreshes settings from the DB, so tests that
    need a config to stick must write it there (mutating settings.<attr> alone
    gets overwritten on the next request).
    """
    record = await KeyValue.filter(key="settings").first()
    config = dict(record.value or {})
    config[key] = value
    record.value = config
    await record.save()
    settings.user_config = config


async def _share_text(client, text="hello integration", expire_value=1, expire_style="day"):
    response = await client.post(
        "/share/text",
        data={
            "text": text,
            "expire_value": str(expire_value),
            "expire_style": expire_style,
        },
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["code"]


async def _share_file(client, name, payload, expire_style="day"):
    response = await client.post(
        "/share/file",
        data={"expire_value": "1", "expire_style": expire_style},
        files={"file": (name, io.BytesIO(payload), "application/octet-stream")},
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["code"]


async def _select(client, code):
    response = await client.post("/share/select", json={"code": code})
    assert response.status_code == 200, response.text
    return response.json()


async def _download(client, download_url, headers=None, expected=200):
    response = await client.get(download_url, headers=headers or {})
    assert response.status_code == expected, response.text
    return response


@pytest.mark.usefixtures("initialized_client")
class TestFileShareJourney:
    async def test_upload_select_download_roundtrip(self, client):
        payload = bytes(range(256)) * 64
        code = await _share_file(client, "trip.bin", payload)
        detail = (await _select(client, code))["detail"]
        response = await _download(client, detail["download_url"])
        assert response.headers["content-type"].startswith("application/octet-stream")
        assert "attachment" in response.headers["content-disposition"]
        assert response.content == payload

    async def test_range_download_returns_206_slices(self, client):
        payload = bytes(range(256)) * 64
        code = await _share_file(client, "range.bin", payload)
        detail = (await _select(client, code))["detail"]
        url = detail["download_url"]

        head = await _download(client, url, headers={"Range": "bytes=0-99"}, expected=206)
        assert head.content == payload[:100]
        assert head.headers["content-range"] == f"bytes 0-99/{len(payload)}"

        tail = await _download(client, url, headers={"Range": f"bytes=100-{len(payload)-1}"}, expected=206)
        assert tail.content == payload[100:]

        out_of_range = await client.get(url, headers={"Range": "bytes=999999999-"})
        assert out_of_range.status_code == 416

    async def test_text_share_roundtrip(self, client):
        code = await _share_text(client, "hello integration")
        detail = (await _select(client, code))["detail"]
        assert detail["text"] == "hello integration"

    async def test_count_limited_code_fails_after_exhaustion(self, client):
        code = await _share_text(client, "one-shot", expire_style="count", expire_value=1)
        await _select(client, code)  # consumes the single allowed use
        exhausted = await _select(client, code)
        assert exhausted["code"] == 404


@pytest.mark.usefixtures("initialized_client")
class TestChunkUploadJourney:
    CHUNK_SIZE = 64

    async def _init_session(self, client, payloads, name="chunk.bin"):
        file_size = sum(len(p) for p in payloads)
        response = await client.post(
            "/chunk/upload/init/",
            json={
                "file_name": name,
                "chunk_size": self.CHUNK_SIZE,
                "file_size": file_size,
                "file_hash": "0" * 64,
            },
        )
        assert response.status_code == 200, response.text
        return response.json()["detail"]["upload_id"]

    async def _upload_chunk(self, client, upload_id, index, payload):
        response = await client.post(
            f"/chunk/upload/chunk/{upload_id}/{index}",
            files={"chunk": (f"part{index}", io.BytesIO(payload), "application/octet-stream")},
        )
        return response

    async def test_full_chunk_upload_merge_and_download(self, client):
        payloads = [bytes([65 + i]) * self.CHUNK_SIZE for i in range(3)]
        upload_id = await self._init_session(client, payloads)

        for index, chunk in enumerate(payloads):
            response = await self._upload_chunk(client, upload_id, index, chunk)
            assert response.status_code == 200, response.text

        response = await client.post(
            f"/chunk/upload/complete/{upload_id}",
            data={"expire_value": "1", "expire_style": "day"},
        )
        assert response.status_code == 200, response.text
        code = response.json()["detail"]["code"]

        detail = (await _select(client, code))["detail"]
        response = await _download(client, detail["download_url"])
        assert response.content == b"".join(payloads)

    async def test_chunk_oversize_rejected(self, client):
        payloads = [b"x" * (self.CHUNK_SIZE + 1)]
        upload_id = await self._init_session(client, payloads)
        response = await self._upload_chunk(client, upload_id, 0, payloads[0])
        assert response.status_code == 400, response.text

    async def test_invalid_chunk_index_rejected(self, client):
        payloads = [b"x" * self.CHUNK_SIZE]
        upload_id = await self._init_session(client, payloads)
        response = await self._upload_chunk(client, upload_id, 99, payloads[0])
        assert response.status_code == 400, response.text

    async def test_cancel_upload_cleans_session(self, client):
        payloads = [b"x" * self.CHUNK_SIZE, b"y" * self.CHUNK_SIZE]
        upload_id = await self._init_session(client, payloads)

        response = await client.delete(f"/chunk/upload/{upload_id}")
        assert response.status_code == 200, response.text

        # Session and chunk records must be gone from the DB. (Asserting on the
        # status endpoint instead would depend on the 404 handler, which needs
        # a built theme to render in bare checkouts.)
        from apps.base.models import UploadChunk

        assert not await UploadChunk.filter(upload_id=upload_id).exists()


@pytest.mark.usefixtures("initialized_client")
class TestUploadAuth:
    async def test_guest_upload_allowed_when_open_upload_on(self, client):
        await _set_db_config("open_upload", 1)
        code = await _share_text(client, "guest ok")
        assert code

    async def test_upload_requires_login_when_guest_upload_off(self, client):
        await _set_db_config("open_upload", 0)
        response = await client.post(
            "/share/text",
            data={"text": "no guest", "expire_value": "1", "expire_style": "day"},
        )
        assert response.status_code == 403, response.text

        token = await _login(client)
        response = await client.post(
            "/share/text",
            data={"text": "admin ok", "expire_value": "1", "expire_style": "day"},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200, response.text

    async def test_admin_endpoints_reject_missing_token(self, client):
        response = await client.get("/admin/file/list/")
        assert response.status_code == 401, response.text
