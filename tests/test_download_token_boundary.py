"""Download endpoint edge paths: token verification failure modes.

Covers the negative space of /share/download — the constant-time token
comparison must reject malformed keys with 403 while still accepting both
the current and the previous time-window token (boundary race tolerance).
"""
import pytest

from core.utils import get_select_token


@pytest.mark.asyncio
class TestDownloadTokenBoundary:
    async def test_wrong_key_is_rejected_with_403(self, initialized_client):
        share = await initialized_client.post(
            "/share/text", data={"text": "token fixture", "expire_style": "day"}
        )
        assert share.status_code == 200
        code = share.json()["detail"]["code"]

        response = await initialized_client.get(
            "/share/download", params={"key": "0" * 64, "code": code}
        )
        assert response.status_code == 403

    async def test_both_time_window_tokens_are_accepted(self, initialized_client):
        share = await initialized_client.post(
            "/share/text", data={"text": "token fixture", "expire_style": "day"}
        )
        assert share.status_code == 200
        code = share.json()["detail"]["code"]

        for offset in (0, 1):
            token = await get_select_token(code, offset=offset)
            response = await initialized_client.get(
                "/share/download", params={"key": token, "code": code}
            )
            assert response.status_code == 200, f"offset={offset}"

    async def test_token_of_other_code_is_rejected(self, initialized_client):
        share = await initialized_client.post(
            "/share/text", data={"text": "token fixture", "expire_style": "day"}
        )
        assert share.status_code == 200
        code = share.json()["detail"]["code"]

        foreign_token = await get_select_token("other-code", offset=0)
        response = await initialized_client.get(
            "/share/download", params={"key": foreign_token, "code": code}
        )
        assert response.status_code == 403
