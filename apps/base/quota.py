import datetime

from fastapi import HTTPException
from tortoise import connections
from tortoise.expressions import Q
from tortoise.functions import Sum

from apps.base.models import FileCodes, StorageReservation
from apps.base.local_share import LOCAL_REF_MARKER
from core.settings import settings
from core.utils import get_now


def owned_storage_queryset(queryset=None):
    """FileCodes that occupy FileCodeBox storage (exclude NAS local-ref rows).

    SQL ``file_path != 'local-ref'`` drops NULLs, so keep null paths explicitly.
    """
    qs = FileCodes.all() if queryset is None else queryset
    return qs.filter(Q(file_path__isnull=True) | ~Q(file_path=LOCAL_REF_MARKER))


def _detect_sql_dialect() -> str:
    """识别当前默认连接的 SQL 方言。

    优先使用 Tortoise capabilities.dialect；
    回退到 db_config 中的 engine 路径字符串。
    """
    conn = connections.get("default")
    dialect = getattr(getattr(conn, "capabilities", None), "dialect", "") or ""
    if dialect:
        return dialect.lower()

    try:
        engine = str(connections.db_config.get("default", {}).get("engine", "")).lower()
    except Exception:
        engine = ""
    if "postgres" in engine or "asyncpg" in engine or "psycopg" in engine:
        return "postgres"
    if "mysql" in engine:
        return "mysql"
    if "sqlite" in engine:
        return "sqlite"
    return "sqlite"


def _sql_placeholders(count: int) -> list[str]:
    """根据数据库方言生成参数占位符（多数据库兼容）。

    SQLite 用 ?，PostgreSQL 用 $1/$2/...，MySQL 用 %s。
    """
    dialect = _detect_sql_dialect()
    if dialect in {"postgres", "postgresql"}:
        return [f"${i}" for i in range(1, count + 1)]
    if dialect == "mysql":
        return ["%s"] * count
    return ["?"] * count


def get_storage_limit() -> int:
    try:
        return max(0, int(getattr(settings, "storage_limit", 0)))
    except (TypeError, ValueError):
        return 0


async def get_storage_usage() -> dict[str, int | None]:
    now = await get_now()
    # SQL 聚合：此函数在每次上传配额检查时调用，禁止全表拉取（D3）
    # 成功文件只计 FileCodes；寄件上传残留保留在容量预留中直到删除成功。
    used_rows = await owned_storage_queryset().annotate(total=Sum("size")).values("total")
    reserved_rows = await StorageReservation.filter(Q(expires_at__gt=now) | Q(delivery_id__isnull=False)).annotate(
        total=Sum("size")
    ).values("total")
    limit = get_storage_limit()
    used_bytes = used_rows[0]["total"] or 0
    reserved_bytes = reserved_rows[0]["total"] or 0
    return {
        "limit": limit,
        "used": used_bytes,
        "reserved": reserved_bytes,
        "available": max(0, limit - used_bytes - reserved_bytes) if limit else None,
    }


async def reserve_storage(token: str, size: int, ttl_seconds: int) -> None:
    requested_size = max(0, int(size))
    limit = get_storage_limit()
    # 普通上传前缀映射到同一寄件预留，避免次数和容量分别产生重复计费行。
    delivery_token = token.split(":", 1)[-1]
    if delivery_token.startswith("d_"):
        now = await get_now()
        conn = connections.get("default")
        p = _sql_placeholders(8)
        changed, _ = await conn.execute_query(
            f"UPDATE storagereservation SET size = {p[0]}, expires_at = {p[1]} "
            f"WHERE token = {p[2]} AND delivery_id IS NOT NULL AND status IN ('pending', 'finalizing') "
            f"AND ({p[3]} = 0 OR "
            f"COALESCE((SELECT SUM(size) FROM filecodes WHERE file_path IS NULL OR file_path != '{LOCAL_REF_MARKER}'), 0) "
            f"+ COALESCE((SELECT SUM(size) FROM storagereservation WHERE token != {p[4]} AND (expires_at > {p[5]} OR delivery_id IS NOT NULL)), 0) "
            f"+ {p[6]} <= {p[7]})",
            [requested_size, now + datetime.timedelta(seconds=ttl_seconds), delivery_token,
             limit, delivery_token, now, requested_size, limit],
        )
        if changed != 1:
            raise HTTPException(507, "上传会话失效或存储容量不足")
        return
    if not limit or requested_size == 0:
        return

    now = await get_now()
    expires_at = now + datetime.timedelta(seconds=ttl_seconds)
    conn = connections.get("default")
    await StorageReservation.filter(token=token, expires_at__lte=now).delete()
    existing = await StorageReservation.filter(token=token, expires_at__gt=now).first()
    if existing:
        if existing.size == requested_size:
            return
        raise HTTPException(status_code=409, detail="上传容量预留信息不一致")

    try:
        ph = _sql_placeholders(6)
        affected, _ = await conn.execute_query(
            f"""
            INSERT INTO storagereservation (token, size, expires_at)
            SELECT {ph[0]}, {ph[1]}, {ph[2]}
            WHERE (
                COALESCE((SELECT SUM(size) FROM filecodes WHERE file_path IS NULL OR file_path != '{LOCAL_REF_MARKER}'), 0)
                + COALESCE((SELECT SUM(size) FROM storagereservation WHERE expires_at > {ph[3]} OR delivery_id IS NOT NULL), 0)
                + {ph[4]}
            ) <= {ph[5]}
            """,
            [token, requested_size, expires_at, now, requested_size, limit],
        )
    except Exception:
        concurrent = await StorageReservation.filter(
            token=token, size=requested_size, expires_at__gt=now
        ).exists()
        if concurrent:
            return
        raise
    if affected != 1:
        concurrent = await StorageReservation.filter(
            token=token, size=requested_size, expires_at__gt=now
        ).exists()
        if concurrent:
            return
        raise HTTPException(status_code=507, detail="存储空间已达到管理员设置的容量上限")


async def release_storage(token: str) -> None:
    # 寄件预留必须先完成文件提交或清理，不能由普通 finally 提前释放容量。
    if token.split(":", 1)[-1].startswith("d_"):
        return
    await StorageReservation.filter(token=token).delete()
