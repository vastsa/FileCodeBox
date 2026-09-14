"""API contract guard: responses must carry snake_case keys only.

Regression net for the D7 lesson: a camel+snake dual-field contract crept
back through build_public_config/build_public_meta (file-based scoping hid
that they serve a live endpoint). Any key matching [a-z]+[A-Z] camel shape
anywhere in these documented response payloads now fails the suite.
"""
import re

import httpx
import pytest

CAMEL_KEY = re.compile(r"^[a-z0-9]+(?:[A-Z][a-zA-Z0-9]*)+$")


def _assert_no_camel_keys(node, path, violations):
    if isinstance(node, dict):
        for key, value in node.items():
            key_path = f"{path}.{key}"
            if isinstance(key, str) and CAMEL_KEY.match(key):
                violations.append(key_path)
            _assert_no_camel_keys(value, key_path, violations)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            _assert_no_camel_keys(item, f"{path}[{index}]", violations)


async def _login(client: httpx.AsyncClient) -> str:
    from tests.conftest import TEST_ADMIN_PASSWORD

    response = await client.post(
        "/admin/login", json={"password": TEST_ADMIN_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["detail"]["token"]


def _check_contract(payload: dict, url: str) -> None:
    violations = []
    _assert_no_camel_keys(payload, url, violations)
    assert not violations, f"camelCase keys leaked into {url}: {violations}"


@pytest.mark.asyncio
class TestApiContractSnakeCase:
    async def test_public_config(self, initialized_client):
        response = await initialized_client.get("/api/v1/config")
        assert response.status_code == 200
        _check_contract(response.json(), "/api/v1/config")

    async def test_dashboard(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/dashboard", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        _check_contract(response.json(), "/admin/dashboard")

    async def test_admin_file_list(self, initialized_client):
        token = await _login(initialized_client)
        response = await initialized_client.get(
            "/admin/file/list", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 200
        _check_contract(response.json(), "/admin/file/list")

    async def test_share_metadata(self, initialized_client):
        share = await initialized_client.post(
            "/share/text/", data={"text": "contract guard", "expire_value": 1, "expire_style": "day"}
        )
        assert share.status_code == 200, share.text
        code = share.json()["detail"]["code"]
        response = await initialized_client.get(
            "/share/metadata/", params={"code": code}
        )
        assert response.status_code == 200
        _check_contract(response.json(), "/share/metadata/")
