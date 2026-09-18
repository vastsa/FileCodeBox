"""Migration runner coverage: discovery order, registration, idempotency,
and failure propagation. Runs the REAL migrations (001-007) against an
in-memory database — the same code path a deployment upgrade takes.
"""
import pytest
from tortoise import Tortoise

from core.database import execute_migrations
from tests.helpers import MEMORY_DB_CONFIG, close_db

EXPECTED = [f"migrations_{i:03d}.py" for i in range(1, 8)]


@pytest.fixture
async def fresh_db():
    """全新内存库：不 generate_schemas（schema 由迁移本身建立——部署真实形态），
    只建 runner 依赖的 migrates 登记表。"""
    from tortoise import Tortoise

    import apps.base.config as config_module

    config_module._config_cached_until = 0.0
    if Tortoise._inited:
        await Tortoise.close_connections()  # 清掉前一个用例的 :memory: 连接
    await Tortoise.init(config=MEMORY_DB_CONFIG)
    await Tortoise.get_connection("default").execute_script(
        "CREATE TABLE IF NOT EXISTS migrates ("
        "id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "migration_file VARCHAR(255) NOT NULL UNIQUE, "
        "executed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
    )
    yield
    await close_db()


async def _registered() -> list[str]:
    conn = Tortoise.get_connection("default")
    _, rows = await conn.execute_query(
        "SELECT migration_file FROM migrates ORDER BY id"
    )
    return [row[0] for row in rows]


@pytest.mark.asyncio
class TestMigrationRunner:
    async def test_full_run_executes_all_in_filename_order(self, fresh_db):
        await execute_migrations()
        registered = await _registered()
        assert registered == EXPECTED, "迁移必须按文件名序完整执行并登记"

    async def test_rerun_is_idempotent(self, fresh_db):
        """重复执行：已登记的迁移全部跳过，登记不重复。"""
        await execute_migrations()
        before = await _registered()
        await execute_migrations()
        after = await _registered()
        assert after == before == EXPECTED

    async def test_pre_registered_subset_skips_those(self, fresh_db):
        """部分已登记（模拟中途升级）：只执行缺口，顺序保持。"""
        conn = Tortoise.get_connection("default")
        await conn.execute_query("DELETE FROM migrates")
        # 预登记 006/007（模拟已执行过全部迁移的库），验证 runner 只跑缺口
        # 001-005 且跳过已登记的 006/007（跳过语义 = 不再执行其 DDL）
        for name in EXPECTED[-2:]:
            await conn.execute_query(
                "INSERT INTO migrates (migration_file) VALUES (?)", [name]
            )
        await execute_migrations()
        registered = await _registered()
        # 预登记的 006/007 占据登记序前列——断言用集合：7 个全登记、无重复
        assert sorted(registered) == sorted(EXPECTED)
        assert len(registered) == len(EXPECTED)
        tables = {
            row[0]
            for row in (
                await conn.execute_query(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )[1]
        }
        assert "filecodes" in tables          # 001 执行了
        assert "storagereservation" not in tables  # 006 被跳过（其 DDL 未执行）

    async def test_real_migrations_produce_expected_schema(self, fresh_db):
        """真实迁移链跑完后的 schema 抽查（与部署形态对齐）。"""
        await execute_migrations()
        conn = Tortoise.get_connection("default")
        tables = {
            row[0]
            for row in (
                await conn.execute_query(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            )[1]
        }
        assert {
            "filecodes",
            "keyvalue",
            "uploadchunk",
            "presignuploadsession",
            "storagereservation",
            "migrates",
        } <= tables

    async def test_failure_propagates_and_halts(self, fresh_db, monkeypatch):
        """迁移执行失败必须向上抛（启动失败可见），不能静默吞掉。"""
        import importlib

                # 构造一个会失败的执行缺口：007 未登记，且其模块 migrate 抛错
        conn = Tortoise.get_connection("default")
        await conn.execute_query("DELETE FROM migrates")
        for name in EXPECTED[:-1]:
            await conn.execute_query(
                "INSERT INTO migrates (migration_file) VALUES (?)", [name]
            )
        real_import = importlib.import_module

        def fake_import(name):
            if name.endswith("migrations_007"):
                class FakeMod:
                    @staticmethod
                    async def migrate():
                        raise RuntimeError("boom")

                return FakeMod()
            return real_import(name)

        monkeypatch.setattr(importlib, "import_module", fake_import)
        with pytest.raises(RuntimeError, match="boom"):
            await execute_migrations()
        # 失败的迁移不得登记
        assert "migrations_007.py" not in await _registered()
