"""D3 回归：dashboard 与配额使用 SQL 聚合，不再整表载入。

用混合数据（文本/文件、过期/活跃、分块）验证聚合结果与语义一致。
"""
import asyncio
import datetime
import unittest

from tortoise import Tortoise

from apps.admin.services import FileService
from apps.admin.views import dashboard
from apps.base.models import FileCodes
from apps.base.quota import get_storage_usage
from tests.helpers import init_memory_db
from core.utils import get_now


class DashboardQuotaAggregationTests(unittest.TestCase):
    def test_dashboard_counters_and_storage_usage_match_data(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        await init_memory_db()
        try:
            now = await get_now()
            past = now - datetime.timedelta(days=2)
            future = now + datetime.timedelta(days=30)

            # 活跃文件（时间式）
            await FileCodes.create(
                code="f1", size=100, expired_count=-1, expired_at=future,
                text=None, prefix="doc", suffix=".txt",
            )
            # 已过期（时间式）
            await FileCodes.create(
                code="f2", size=200, expired_count=-1, expired_at=past,
                text=None, prefix="old", suffix=".bin",
            )
            # 次数耗尽（count 式，带过期时间）
            await FileCodes.create(
                code="f3", size=300, expired_count=0, expired_at=future,
                text=None, prefix="cnt", suffix=".zip",
            )
            # 文本分享
            await FileCodes.create(
                code="t1", size=50, expired_count=-1, expired_at=future,
                text="hello",
            )
            # 永久
            await FileCodes.create(
                code="p1", size=400, expired_count=-1, expired_at=None, text=None
            )

            detail = (await dashboard(FileService())).detail

            self.assertEqual(detail["totalFiles"], 5)
            self.assertEqual(detail["storageUsed"], "1050")
            self.assertEqual(detail["expiredCount"], 2, "时间过期+次数耗尽都算过期")
            self.assertEqual(detail["activeCount"], 3)
            self.assertEqual(detail["textCount"], 1)
            self.assertEqual(detail["fileCount"], 4)
            self.assertEqual(detail["usedCount"], 0)

            usage = await get_storage_usage()
            self.assertEqual(usage["used"], 1050, "配额聚合应与手工求和一致")
            self.assertIsNone(usage["available"])  # 未设 storage_limit
        finally:
            await Tortoise.close_connections()
            from tests.helpers import close_db as _c
            await _c()


if __name__ == "__main__":
    unittest.main()
