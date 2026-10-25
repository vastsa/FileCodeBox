"""SQLite 连接 PRAGMA 生效性验证。

不 mock 配置字典，而是用 get_db_config() 真起一个文件库读取 PRAGMA——
Tortoise 的 SqliteClient 在 create_connection() 时逐条执行 credentials 中的
PRAGMA，只有真实连接才能验证这一点。
"""
import pytest
from tortoise import Tortoise

import core.database as database
from tests.helpers import close_db


@pytest.fixture
async def file_db(tmp_path, monkeypatch):
    monkeypatch.setattr(database, "_DB_FILE", str(tmp_path / "pragma.db"))
    if Tortoise._inited:
        await Tortoise.close_connections()
    await Tortoise.init(config=database.get_db_config())
    try:
        yield Tortoise.get_connection("default")
    finally:
        await close_db()


async def _pragma(conn, statement: str):
    rows = await conn.execute_query_dict(statement)
    return next(iter(rows[0].values()))


@pytest.mark.asyncio
class TestSqlitePragmas:
    async def test_wal_and_busy_timeout_kept(self, file_db):
        assert str(await _pragma(file_db, "PRAGMA journal_mode")).lower() == "wal"
        assert await _pragma(file_db, "PRAGMA busy_timeout") == 10000

    async def test_synchronous_normal(self, file_db):
        # 1 = NORMAL（WAL 下省 fsync），2 = FULL
        assert await _pragma(file_db, "PRAGMA synchronous") == 1

    async def test_temp_store_memory(self, file_db):
        # 0 = DEFAULT，1 = FILE，2 = MEMORY
        assert await _pragma(file_db, "PRAGMA temp_store") == 2

    async def test_cache_size_8mb(self, file_db):
        # 负值单位为 KiB
        assert await _pragma(file_db, "PRAGMA cache_size") == -8000

    async def test_foreign_keys_on(self, file_db):
        assert await _pragma(file_db, "PRAGMA foreign_keys") == 1
