"""Pytest fixtures for integration tests (real ASGI chain via httpx).

The legacy unittest suite keeps its own style (helpers.SettingsOverrideMixin);
these fixtures are for new pytest-style tests. Lifespan is intentionally NOT
run: it would init the real file DB and start background tasks. Instead the
``db`` fixture inits an in-memory DB, which the per-request middleware and the
handlers then use normally.
"""
import shutil

import httpx
import pytest_asyncio

import main
from core.settings import data_root
from tests.helpers import close_db, init_memory_db

TEST_ADMIN_PASSWORD = "Integration-Test-12345"


@pytest_asyncio.fixture
async def db():
    await init_memory_db()
    try:
        yield
    finally:
        await close_db()


@pytest_asyncio.fixture
async def client(db):
    # Rate limiters are process-global; clear them so tests never trip 429.
    from apps.base.utils import ip_limit

    for limiter in ip_limit.values():
        limiter.ips.clear()
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", follow_redirects=True
    ) as c:
        yield c


@pytest_asyncio.fixture
async def initialized_client(client):
    """App with the system set up via POST /setup (admin password known)."""
    response = await client.post(
        "/setup",
        json={
            "admin_password": TEST_ADMIN_PASSWORD,
            "confirm_password": TEST_ADMIN_PASSWORD,
            "site_name": "integration-tests",
            "expire_style": ["day", "forever", "count"],
        },
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 200, response.text
    # initialize_system wrote config into the in-memory DB; restore the
    # process-global settings snapshot afterwards so other tests see defaults.
    from core.settings import settings

    original_user_config = dict(settings.user_config)
    try:
        yield client
    finally:
        settings.user_config = original_user_config
        # Uploads in tests land under <repo>/data/share; remove them so the
        # working tree stays clean (the DB itself is in-memory).
        shutil.rmtree(f"{data_root}/share", ignore_errors=True)
