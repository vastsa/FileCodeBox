import datetime

from fastapi import HTTPException
from tortoise import connections

from apps.base.models import FileCodes, StorageReservation
from core.settings import settings
from core.utils import get_now


def _sql_placeholders(count: int) -> list[str]:
    """根据数据库类型生成参数占位符（多数据库兼容）。

    SQLite 用 ?，PostgreSQL 用 $1/$2/...，MySQL 用 %s。
    """
    conn = connections.get("default")
    engine = getattr(conn, "engine", "") or ""
    if "postgres" in engine:
        return [f"${i}" for i in range(1, count + 1)]
    if "mysql" in engine:
        return ["%s"] * count
    return ["?"] * count


def get_storage_limit() -> int:
    try:
        return max(0, int(getattr(settings, "storageLimit", 0)))
    except (TypeError, ValueError):
        return 0


async def get_storage_usage() -> dict[str, int | None]:
    now = await get_now()
    used = await FileCodes.all().values_list("size", flat=True)
    reserved = await StorageReservation.filter(expires_at__gt=now).values_list(
        "size", flat=True
    )
    limit = get_storage_limit()
    used_bytes = sum(used)
    reserved_bytes = sum(reserved)
    return {
        "limit": limit,
        "used": used_bytes,
        "reserved": reserved_bytes,
        "available": max(0, limit - used_bytes - reserved_bytes) if limit else None,
    }


async def reserve_storage(token: str, size: int, ttl_seconds: int) -> None:
    requested_size = max(0, int(size))
    limit = get_storage_limit()
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
                COALESCE((SELECT SUM(size) FROM filecodes), 0)
                + COALESCE((SELECT SUM(size) FROM storagereservation WHERE expires_at > {ph[3]}), 0)
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
    await StorageReservation.filter(token=token).delete()
