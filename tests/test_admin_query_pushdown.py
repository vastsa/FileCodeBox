"""后台列表/健康摘要的 SQL 下推等价性测试。

list_files 与 build_file_health_summary 已从"整表加载 + 内存过滤"
改为 SQL 过滤/排序/分页 + SQL 计数。这里用已知数据集把 SQL 结果与
逐行 Python 规则（_build_admin_file_item + _match_admin_file*）对照，
防止过滤、排序、统计语义在改写后漂移。
"""
import datetime

import pytest

from apps.admin.services import FileService
from apps.base.models import FileCodes
from core.utils import get_now


async def _seed():
    now = await get_now()
    rows = [
        dict(code="active01", prefix="report", suffix=".txt", size=100,
             file_path="share/data/a", uuid_file_name="u1",
             expired_at=now + datetime.timedelta(days=30), expired_count=-1),
        dict(code="expired1", prefix="old", suffix=".bin", size=200,
             file_path="share/data/b", uuid_file_name="u2",
             expired_at=now - datetime.timedelta(days=2), expired_count=-1, used_count=3),
        dict(code="count000", prefix="cnt", suffix=".zip", size=300,
             file_path="share/data/c", uuid_file_name="u3",
             expired_at=now + datetime.timedelta(days=10), expired_count=0),
        dict(code="cntnull0", prefix="cntnull", suffix=".zip", size=350,
             file_path="share/data/c2", uuid_file_name="u3b",
             expired_at=None, expired_count=0),
        dict(code="text0001", prefix="", suffix="", size=50, text="hello world 密码",
             expired_at=now + datetime.timedelta(days=5), expired_count=-1, used_count=2),
        dict(code="soon0001", prefix="soon", suffix=".tmp", size=400,
             file_path="share/data/d", uuid_file_name="u4",
             expired_at=now + datetime.timedelta(hours=2), expired_count=-1, used_count=1),
        dict(code="perm0001", prefix="keep", suffix=".dat", size=500,
             file_path="share/data/e", uuid_file_name="u5",
             expired_at=None, expired_count=-1),
        dict(code="broken01", prefix="lost", suffix=".raw", size=600,
             expired_at=now + datetime.timedelta(days=20), expired_count=-1),
        dict(code="chunk001", prefix="movie", suffix=".mp4", size=700,
             file_path="share/data/f", uuid_file_name="u6", is_chunked=True,
             expired_at=now + datetime.timedelta(days=7), expired_count=-1, used_count=5),
        dict(code="abcdefg1", prefix="abcd", suffix="efg", size=800,
             file_path="share/data/g", uuid_file_name="u7",
             expired_at=now + datetime.timedelta(days=15), expired_count=-1),
        dict(code="special1", prefix="", suffix="", size=25, text="100%_done",
             expired_at=now + datetime.timedelta(days=3), expired_count=-1),
    ]
    for row in rows:
        await FileCodes.create(**row)
    # 按主键序返回，等价于旧实现的遍历顺序（内存排序是稳定排序）
    return await FileCodes.all(), now


def _aggregate_health(items) -> dict:
    """旧版 _accumulate_health_summary 的逐行语义。"""
    summary = FileService()._empty_health_summary()
    for item in items:
        insights = item["status_insights"]
        reasons = insights["reasons"]
        severity = insights["severity"]
        state = insights["state"]
        if severity in {"danger", "warning"}:
            summary["health_attention_count"] += 1
        if severity == "danger":
            summary["health_danger_count"] += 1
        if severity == "warning":
            summary["health_warning_count"] += 1
        if severity == "success":
            summary["healthy_count"] += 1
        if state == "permanent":
            summary["permanent_count"] += 1
        if "expires_soon" in reasons:
            summary["expiring_soon_count"] += 1
        if "storage_metadata_incomplete" in reasons:
            summary["storage_issue_count"] += 1
        if "never_retrieved" in reasons:
            summary["never_retrieved_count"] += 1
    return summary


@pytest.fixture
async def seeded(db):
    service = FileService()
    rows, now = await _seed()
    items = [await service._build_admin_file_item(row, now=now) for row in rows]
    return service, rows, items, now


@pytest.mark.asyncio
class TestListFilesPushdown:
    @pytest.mark.parametrize(
        "health",
        ["attention", "danger", "warning", "expired", "expiring_soon",
         "storage_issue", "never_retrieved", "healthy", "permanent"],
    )
    async def test_health_filter_matches_python_rules(self, seeded, health):
        service, _rows, items, _now = seeded
        expected = [
            item["id"]
            for item in items
            if service._match_admin_file_health(item, health)
        ]
        files, total, _summary = await service.list_files(1, 100, health=health)
        assert total == len(expected)
        assert {f["id"] for f in files} == set(expected)

    @pytest.mark.parametrize("status", ["active", "expired"])
    @pytest.mark.parametrize("file_type", ["text", "file", "chunked"])
    async def test_status_and_type_filter_matches_python_rules(
        self, seeded, status, file_type
    ):
        service, _rows, items, _now = seeded
        expected = [
            item["id"]
            for item in items
            if service._match_admin_file(item, "", status, file_type, "")
        ]
        files, total, _summary = await service.list_files(
            1, 100, status=status, file_type=file_type
        )
        assert total == len(expected)
        assert {f["id"] for f in files} == set(expected)

    @pytest.mark.parametrize("keyword", ["report", "密码", "cde", "100%_", "SPECIAL1"])
    async def test_keyword_matches_python_rules(self, seeded, keyword):
        service, _rows, items, _now = seeded
        lowered = keyword.strip().lower()
        expected = [
            item["id"]
            for item in items
            if service._match_admin_file(item, lowered, "", "", "")
        ]
        files, total, _summary = await service.list_files(1, 100, keyword=keyword)
        assert total == len(expected)
        assert {f["id"] for f in files} == set(expected)

    async def test_boundary_spanning_name_keyword_matches(self, seeded):
        service, _rows, _items, _now = seeded
        files, _total, _summary = await service.list_files(1, 100, keyword="cde")
        assert [f["code"] for f in files] == ["abcdefg1"]

    @pytest.mark.parametrize(
        "sort_by", ["created_at", "expired_at", "name", "size", "used_count", "code"]
    )
    @pytest.mark.parametrize("sort_order", ["asc", "desc"])
    async def test_sort_matches_stable_python_sort(
        self, seeded, sort_by, sort_order
    ):
        service, _rows, items, _now = seeded
        expected = sorted(
            items,
            key=lambda item: service._get_sort_value(item, sort_by),
            reverse=sort_order == "desc",
        )
        files, _total, _summary = await service.list_files(
            1, 100, sort_by=sort_by, sort_order=sort_order
        )
        assert [f["id"] for f in files] == [item["id"] for item in expected]

    async def test_pagination_and_summary(self, seeded, monkeypatch):
        service, rows, items, _now = seeded
        calls = []
        real_build = service._build_admin_file_item

        async def counting(file_code, now=None):
            calls.append(file_code.id)
            return await real_build(file_code, now=now)

        monkeypatch.setattr(service, "_build_admin_file_item", counting)

        files, total, summary = await service.list_files(2, 3)
        assert total == len(items)
        expected_order = sorted(
            items,
            key=lambda item: service._get_sort_value(item, "created_at"),
            reverse=True,
        )
        assert [f["id"] for f in files] == [
            item["id"] for item in expected_order[3:6]
        ]
        assert len(calls) == 3, "只应为当前页构建详情，不能整表逐行加工"

        expected_summary = {
            "total_files": len(items),
            "active_count": sum(1 for i in items if not i["is_expired"]),
            "expired_count": sum(1 for i in items if i["is_expired"]),
            "text_count": sum(1 for i in items if i["is_text"]),
            "chunked_count": sum(1 for i in items if i["is_chunked"]),
            "storage_used": sum(
                i["size"] for i in items if i["file_path"] != "local-ref"
            ),
            "used_count": sum(i["used_count"] for i in items),
        }
        expected_summary["file_count"] = (
            expected_summary["total_files"] - expected_summary["text_count"]
        )
        expected_summary.update(_aggregate_health(items))
        assert summary == expected_summary


@pytest.mark.asyncio
class TestHealthSummarySql:
    async def test_health_summary_matches_python_rules(self, seeded):
        service, _rows, items, now = seeded
        assert await service.build_file_health_summary(now=now) == _aggregate_health(items)
