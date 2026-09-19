"""寄件授权与管理：口令校验、令牌续期、数据库分页和配置更新。"""

import json
import secrets

from fastapi import HTTPException
from tortoise.exceptions import IntegrityError
from tortoise.expressions import F, Q
from tortoise.transactions import in_transaction

from apps.admin.dependencies import create_token, verify_token
from apps.base.models import DeliveryCode, StorageReservation
from apps.base.quota import _sql_placeholders
from apps.delivery.storage import validate_storage_config
from core.settings import settings
from core.utils import get_now

TOKEN_TTL = 900


async def upload_identity(authorization: str | None) -> int:
    """只接受用途为 delivery 的凭证；管理员 token 也不能被误当作寄件授权。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "请先验证寄件码")
    try:
        payload = verify_token(authorization[7:])
        if payload.get("purpose") != "delivery" or payload.get("is_admin"):
            raise ValueError("凭证用途错误")
        code_id = int(payload["delivery_id"])
        # 历史令牌按初始版本 1 解释；改码后同样会立即失效。
        token_version = payload.get("delivery_version", 1)
        record = await DeliveryCode.filter(id=code_id, deleted=False).first()
        if record is None or int(token_version) != record.auth_version:
            raise ValueError("寄件码已修改")
        return code_id
    except (ValueError, TypeError, KeyError):
        raise HTTPException(401, "寄件凭证无效或已过期，请重新验证寄件码") from None


async def active_code(code_id: int) -> DeliveryCode:
    record = await DeliveryCode.filter(id=code_id, enabled=True, deleted=False).first()
    if not record or record.expires_at <= await get_now():
        raise HTTPException(403, "寄件码无效、已过期或已停用")
    return record


async def create_code(data):
    """创建时保存原文，便于管理员后续查看；访客响应仍不提供任何口令列表。"""
    validate_storage_config(settings.file_storage if data.storage_type == "system" else data.storage_type)
    code = data.code or "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(16))
    try:
        record = await DeliveryCode.create(
            code_value=code, name=data.name,
            storage_type=data.storage_type, target_path=data.target_path,
            expires_at=data.expires_at, max_uploads=data.max_uploads,
            note=data.note, tags=data.tags,
        )
    except IntegrityError:
        raise HTTPException(409, "该寄件码已被使用，请设置其他口令") from None
    return {"item": await code_summary(record), "code": code}


async def code_summary(record, *, include_code=False):
    """仅供已鉴权的后台读取状态和口令原文，不返回摘要或存储密钥。"""
    now = await get_now()
    state = "active"
    if record.deleted:
        state = "deleted"
    elif record.used_count >= record.max_uploads:
        state = "exhausted"
    elif not record.enabled:
        state = "disabled"
    elif record.expires_at <= now:
        state = "expired"
    return {
        "id": record.id, "name": record.name, "storage_type": record.storage_type,
        **({"code": record.code_value} if include_code else {}),
        "note": record.note, "tags": record.tags if isinstance(record.tags, list) else [],
        "target_path": record.target_path, "expires_at": record.expires_at,
        "max_uploads": record.max_uploads, "used_count": record.used_count,
        "reserved_count": record.reserved_count, "enabled": record.enabled,
        "deleted": record.deleted, "status": state, "created_at": record.created_at,
        "remaining": max(0, record.max_uploads - record.used_count - record.reserved_count),
    }


async def verify_code(code: str):
    record = await DeliveryCode.filter(code_value=code).first()
    if not record:
        raise HTTPException(403, "寄件码无效、已过期或已停用")
    record = await active_code(record.id)
    remaining = record.max_uploads - record.used_count - record.reserved_count
    # 已预占的分片会话允许重新验证后续传，新文件仍由 reserve_slot 拒绝超额。
    if remaining <= 0 and not await StorageReservation.filter(delivery_id=record.id, status__in=["pending", "finalizing"]).exists():
        raise HTTPException(409, "可上传次数已耗尽或正在使用，请联系管理员")
    return await session_summary(record)


async def session_summary(record):
    """验证与续期使用相同白名单响应，不泄露路径、存储密钥或管理员授权。"""
    return {
        "token": create_token({"purpose": "delivery", "delivery_id": record.id,
                               "delivery_version": record.auth_version}, expires_in=TOKEN_TTL),
        "expires_in": TOKEN_TTL, "name": record.name,
        "remaining": max(0, record.max_uploads - record.used_count - record.reserved_count),
        "expires_at": record.expires_at, "upload_size": settings.upload_size,
        "allowed_file_types": settings.allowed_file_types, "expire_style": settings.expire_style,
        "max_save_seconds": settings.max_save_seconds, "enable_chunk": settings.enable_chunk,
    }


async def refresh_session(authorization):
    """有效令牌可续期；改码、删除、手动停用或到期后不能延长权限。"""
    code_id = await upload_identity(authorization)
    record = await DeliveryCode.get(id=code_id)
    # 耗尽自动停用仅允许获取既有完成结果，创建上传仍由原子预占拒绝。
    if record.expires_at <= await get_now() or (not record.enabled and record.used_count < record.max_uploads):
        raise HTTPException(403, "寄件码已过期或停用")
    return await session_summary(record)


async def update_code(code_id, data):
    """原子更新可编辑配置，改码时同步撤销当前版本的临时寄件凭证。"""
    async with in_transaction() as conn:
        record = await DeliveryCode.filter(id=code_id, deleted=False).using_db(conn).first()
        if not record:
            raise HTTPException(404, "寄件码不存在或已删除")
        changes = data.model_dump(exclude_unset=True)
        new_code = changes.pop("code", "")
        # 空值和省略均保持历史口令，因此此前 32 位以上的旧码仍可继续使用。
        if "expires_at" in changes and changes["expires_at"] <= await get_now():
            # 兼容旧管理页完整回传过期时间：未改变期限时允许只编辑备注等字段。
            if changes["expires_at"] != record.expires_at:
                raise HTTPException(400, "新的有效期必须晚于当前时间")
        max_uploads = changes.get("max_uploads", record.max_uploads)
        if record.used_count + record.reserved_count > max_uploads:
            raise HTTPException(409, "上传总次数不能小于已使用次数与上传中占用次数之和，请刷新后重试")
        storage_requested = "storage_type" in changes or "target_path" in changes
        storage_type = changes.get("storage_type", record.storage_type)
        target_path = changes.get("target_path", record.target_path)
        if storage_type == "system":
            target_path = ""
        elif not target_path:
            raise HTTPException(400, "自定义存储位置必须填写目标目录")
        # 整理名称或元数据时不依赖当前后端配置；仅实际改存储设置才重新校验。
        if storage_requested and (storage_type != record.storage_type or target_path != record.target_path):
            validate_storage_config(settings.file_storage if storage_type == "system" else storage_type)
            changes["storage_type"] = storage_type
            changes["target_path"] = target_path
        if new_code and new_code != record.code_value:
            # 版本由数据库递增，两个改码请求并发时任一旧令牌都不会被错误复用。
            changes.update(code_value=new_code, auth_version=True)
        if changes:
            try:
                # 条件写入把已用和预占次数与配置修改放入同一语句，避免并发上传越过新额度。
                bound_fields = [field for field in changes if field != "auth_version"]
                placeholders = _sql_placeholders(len(bound_fields) + 2)
                assignments = ", ".join(f"{field} = {placeholders[index]}" for index, field in enumerate(bound_fields))
                if "auth_version" in changes:
                    assignments += ", auth_version = auth_version + 1"
                changed, _ = await conn.execute_query(
                    f"UPDATE deliverycode SET {assignments} WHERE id = {placeholders[-2]} "
                    f"AND deleted = 0 "
                    f"AND used_count + reserved_count <= {placeholders[-1]}",
                    [json.dumps(changes[field], ensure_ascii=False) if field == "tags" else changes[field]
                     for field in bound_fields] + [record.id, max_uploads],
                )
                if changed != 1:
                    raise HTTPException(409, "上传次数已变化，请刷新后重试")
            except IntegrityError:
                raise HTTPException(409, "该寄件码已被使用，请设置其他口令") from None
        record = await DeliveryCode.get(id=record.id).using_db(conn)
        return await code_summary(record)


async def list_codes(*, page=1, page_size=20, keyword="", status="all", storage_type="all", tag="", sort_by="created_at", sort_order="desc"):
    """筛选、计数、排序和分页全部在数据库执行，列表不返回口令原文。"""
    if status not in {"all", "active", "disabled", "expired", "exhausted"}:
        raise HTTPException(400, "不支持的寄件码状态筛选")
    if storage_type not in {"all", "system", "local", "s3", "webdav"}:
        raise HTTPException(400, "不支持的存储类型筛选")
    if sort_by not in {"created_at", "expires_at", "name", "used_count", "max_uploads"} or sort_order not in {"asc", "desc"}:
        raise HTTPException(400, "不支持的排序方式")
    query = DeliveryCode.filter(deleted=False)
    now = await get_now()
    if status == "exhausted":
        query = query.filter(used_count__gte=F("max_uploads"))
    elif status == "disabled":
        query = query.filter(enabled=False, used_count__lt=F("max_uploads"))
    elif status == "expired":
        query = query.filter(enabled=True, expires_at__lte=now, used_count__lt=F("max_uploads"))
    elif status == "active":
        query = query.filter(enabled=True, expires_at__gt=now, used_count__lt=F("max_uploads"))
    if storage_type != "all":
        query = query.filter(storage_type=storage_type)
    if keyword.strip():
        query = query.filter(Q(name__icontains=keyword.strip()) | Q(note__icontains=keyword.strip()))
    if tag.strip():
        # 当前应用使用 SQLite；JSON 数组逐项精确匹配，不把标签误当成子串。
        from tortoise.expressions import RawSQL
        escaped = tag.strip().replace("'", "''")
        query = query.annotate(tag_match=RawSQL(
            "EXISTS (SELECT 1 FROM json_each(deliverycode.tags) WHERE lower(value) = lower('" + escaped + "'))"
        )).filter(tag_match=1)
    total = await query.count()
    order = ("-" if sort_order == "desc" else "") + sort_by
    # 只选取管理展示字段，口令原文仅由单独管理接口按需返回。
    records = await query.order_by(order, "-id").offset((page - 1) * page_size).limit(page_size).only(
        "id", "name", "note", "tags", "storage_type", "target_path", "expires_at",
        "max_uploads", "used_count", "reserved_count", "enabled", "deleted", "created_at",
    )
    return {"items": [await code_summary(record) for record in records], "total": total}


async def batch_codes(data):
    """批量操作在同一事务中先完整校验，任一记录不合法时整批不变更。"""
    async with in_transaction() as conn:
        records = await DeliveryCode.filter(id__in=data.ids, deleted=False).using_db(conn)
        by_id = {record.id: record for record in records}
        missing = [str(code_id) for code_id in data.ids if code_id not in by_id]
        if missing:
            raise HTTPException(404, "寄件码不存在、已删除或不可用：" + "、".join(missing))
        if data.action == "enable" and any(record.code_value is None for record in records):
            raise HTTPException(409, "所选记录包含没有原文的旧码，请先重新设置寄件码")
        if data.action == "update":
            now = await get_now()
            if data.expires_at is not None and data.expires_at <= now:
                raise HTTPException(400, "新的有效期必须晚于当前时间")
            if data.max_uploads is not None:
                invalid = [str(record.id) for record in records if record.used_count + record.reserved_count > data.max_uploads]
                if invalid:
                    raise HTTPException(409, "上传次数不能小于已使用和上传中占用次数，受影响寄件码：" + "、".join(invalid))
        if data.action == "delete":
            await DeliveryCode.filter(id__in=data.ids).using_db(conn).update(deleted=True, enabled=False, auth_version=F("auth_version") + 1)
            return {"message": "已删除寄件码，已收文件和取件码不受影响", "count": len(data.ids)}
        changes = {"enabled": data.action == "enable"} if data.action in {"enable", "disable"} else {}
        if data.action == "update":
            if data.expires_at is not None:
                changes["expires_at"] = data.expires_at
            if data.max_uploads is not None:
                changes["max_uploads"] = data.max_uploads
        # 批量条件写入必须覆盖全部记录，防止并发上传使其中一个新额度失效。
        placeholders = _sql_placeholders(len(changes) + len(data.ids) + 1)
        assignments = ", ".join(f"{field} = {placeholders[index]}" for index, field in enumerate(changes))
        if data.action in {"enable", "disable"}:
            assignments += ", auth_version = auth_version + 1"
        id_placeholders = ", ".join(placeholders[len(changes):-1])
        condition = ""
        values = list(changes.values()) + data.ids
        if data.action == "update" and data.max_uploads is not None:
            # max_uploads 是 update 时第一个或第二个字段，改用其实际占位符。
            condition = f" AND used_count + reserved_count <= {placeholders[-1]}"
            values.append(data.max_uploads)
        changed, _ = await conn.execute_query(
            f"UPDATE deliverycode SET {assignments} WHERE id IN ({id_placeholders}) "
            f"AND deleted = 0{condition}", values,
        )
        if changed != len(data.ids):
            raise HTTPException(409, "寄件码状态已变化，请刷新后重试")
        result = await DeliveryCode.filter(id__in=data.ids, deleted=False).using_db(conn)
        return {"items": [await code_summary(record) for record in result], "count": len(result)}
