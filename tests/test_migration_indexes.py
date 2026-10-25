"""迁移 008 建立的索引存在且被查询计划实际选用。

跑真实迁移链（不 generate_schemas），与部署升级形态一致；用
EXPLAIN QUERY PLAN 断言索引名出现在执行计划中，避免"建了索引但查询用不上"。
"""
import pytest
from tortoise import Tortoise

import apps.base.config as config_module
from core.database import execute_migrations
from tests.helpers import MEMORY_DB_CONFIG, close_db

INDEXES = {
    "idx_filecodes_expired_at",
    "idx_filecodes_created_at",
    "idx_uploadchunk_upload_chunk",
}


@pytest.fixture
async def migrated_db():
    config_module._config_cached_until = 0.0
    if Tortoise._inited:
        await Tortoise.close_connections()
    await Tortoise.init(config=MEMORY_DB_CONFIG)
    conn = Tortoise.get_connection("default")
    await conn.execute_script(
        "CREATE TABLE IF NOT EXISTS migrates ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "migration_file VARCHAR(255) NOT NULL UNIQUE, "
        "executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    await execute_migrations()
    try:
        yield conn
    finally:
        await close_db()


async def _plan(conn, sql: str) -> str:
    _, rows = await conn.execute_query(f"EXPLAIN QUERY PLAN {sql}")
    return " | ".join(str(row["detail"]) for row in rows)


@pytest.mark.asyncio
class TestMigrationIndexes:
    async def test_indexes_exist(self, migrated_db):
        _, rows = await migrated_db.execute_query(
            "SELECT name FROM sqlite_master WHERE type='index'"
        )
        names = {row["name"] for row in rows}
        assert INDEXES <= names

    async def test_expiry_scan_uses_index(self, migrated_db):
        plan = await _plan(
            migrated_db,
            "SELECT id FROM filecodes WHERE expired_at < '2024-01-01 00:00:00'",
        )
        assert "idx_filecodes_expired_at" in plan

    async def test_recent_listing_uses_created_at_index(self, migrated_db):
        plan = await _plan(
            migrated_db,
            "SELECT id FROM filecodes ORDER BY created_at DESC LIMIT 8",
        )
        assert "idx_filecodes_created_at" in plan

    async def test_chunk_lookup_uses_composite_index(self, migrated_db):
        plan = await _plan(
            migrated_db,
            "SELECT chunk_index FROM uploadchunk "
            "WHERE upload_id = 'abc' AND chunk_index = 3",
        )
        assert "idx_uploadchunk_upload_chunk" in plan

    async def test_chunk_cleanup_uses_upload_id_prefix(self, migrated_db):
        plan = await _plan(
            migrated_db,
            "DELETE FROM uploadchunk WHERE upload_id = 'abc'",
        )
        assert "idx_uploadchunk_upload_chunk" in plan
