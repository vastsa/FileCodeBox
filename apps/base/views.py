import hashlib
import os
import uuid
from datetime import timedelta
from urllib.parse import quote, unquote

from typing import Annotated, Optional, Tuple, Union

from fastapi import APIRouter, Form, Request, UploadFile, File, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from starlette import status
from starlette.responses import Response
from tortoise.expressions import Case, F, Q, When

from apps.base.upload_access import UploadAccess, authorize_upload, prepare_upload, upload_storage, abort_access, completed_upload
from apps.base.models import DeliveryFile
from apps.base.models import FileCodes, UploadChunk, PresignUploadSession
from apps.base.quota import release_storage, reserve_storage
from apps.base.share_storage import delivery_record, storage_for_share
from apps.base.services import (
    PRESIGN_SESSION_EXPIRES,
    FileUploadService,
    response_from_download,
    stored_file_of,
    validate_file_size,
)
from core.storage import StoredFile
from core.logger import logger
from apps.base.schemas import (
    SelectFileModel,
    InitChunkUploadModel,
    CompleteUploadModel,
    PresignUploadInitRequest,
)
from apps.base.file_validation import validate_file_type, validate_upload_file, validate_header_bytes
from apps.base.utils import (
    ip_limit,
    get_chunk_file_path_name,
    validate_expire_style,
)
from core.response import APIResponse
from core.settings import settings
from core.storage import FileStorageInterface, storages as storages
from core.utils import (
    get_file_url as get_proxy_file_url,
    get_select_token,
    get_now,
    sanitize_filename,
)

share_api = APIRouter(prefix="/share", tags=["分享"])


# ============ 公共服务层 ============


def normalize_share_code(code: str) -> str:
    return str(code or "").strip()


@share_api.post("/text/", dependencies=[Depends(authorize_upload)])
async def share_text(
    access: Annotated[UploadAccess, Depends(authorize_upload)] = None,
    text: str = Form(...),
    expire_value: int = Form(default=1, gt=0),
    expire_style: str = Form(default="day"),
    ip: str = Depends(ip_limit["upload"]),
):
    validate_expire_style(expire_style)
    text_size = len(text.encode("utf-8"))
    max_txt_size = 222 * 1024
    if text_size > max_txt_size:
        raise HTTPException(status_code=403, detail="内容过多,建议采用文件形式")

    code = await FileUploadService.create_text_share(text, expire_value, expire_style, access=access)
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code})


@share_api.post("/file/", dependencies=[Depends(authorize_upload)])
async def share_file(
    access: Annotated[UploadAccess, Depends(authorize_upload)] = None,
    expire_value: int = Form(default=1, gt=0),
    expire_style: str = Form(default="day"),
    file: UploadFile = File(...),
    ip: str = Depends(ip_limit["upload"]),
):
    file_size = await validate_file_size(file, settings.upload_size)
    await validate_upload_file(file)
    validate_expire_style(expire_style)
    detail = await FileUploadService.create_file_share(
        file, size=file_size, expire_value=expire_value, expire_style=expire_style, access=access
    )
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail=detail)


async def get_code_file_by_code(
    code: str, check: bool = True
) -> Tuple[bool, Union[FileCodes, str]]:
    normalized_code = normalize_share_code(code)
    if not normalized_code:
        return False, "文件不存在"
    file_code = await FileCodes.filter(code=normalized_code).first()
    if not file_code:
        return False, "文件不存在"
    if await file_code.is_expired() and check:
        return False, "文件已过期"
    return True, file_code


async def consume_file_usage(file_code: FileCodes) -> bool:
    """原子校验分享状态并记录一次实际领取。"""
    now = await get_now()
    eligible = (
        Q(expired_count__gt=0)
        | Q(expired_count__lt=0, expired_at__gt=now)
        | Q(expired_count__lt=0, expired_at=None)
    )
    updated = await FileCodes.filter(Q(id=file_code.id) & eligible).update(
        expired_count=Case(
            When(expired_count__gt=0, then=F("expired_count") - 1),
            default=F("expired_count"),
        ),
        used_count=F("used_count") + 1,
    )
    if not updated:
        return False
    await file_code.refresh_from_db()
    return True


def build_file_metadata(file_code: FileCodes) -> dict:
    is_text = file_code.text is not None
    remaining_downloads = (
        file_code.expired_count if file_code.expired_count > 0 else None
    )
    return {
        "code": file_code.code,
        "name": file_code.prefix + file_code.suffix,
        "size": file_code.size,
        "type": "text" if is_text else "file",
        "is_text": is_text,
        "created_at": file_code.created_at,
        "expired_at": file_code.expired_at,
        "expired_count": file_code.expired_count,
        "used_count": file_code.used_count,
        "remaining_downloads": remaining_downloads,
    }


async def build_select_detail(
    file_code: FileCodes, file_storage: FileStorageInterface
) -> dict:
    metadata = build_file_metadata(file_code)
    if file_code.text is not None:
        download_url = None
    elif file_code.expired_count >= 0 or await delivery_record(file_code) is not None:
        # 有次数限制的文件必须经过下载接口，第三方直链无法阻止重复使用。
        download_url = await get_proxy_file_url(file_code.code)
    else:
        download_url = await file_storage.get_file_url(stored_file_of(file_code))
    content = file_code.text if file_code.text is not None else None
    return {
        **metadata,
        "text": content if content is not None else download_url,
        "content": content,
        "download_url": download_url,
    }


@share_api.get("/metadata/")
async def get_file_metadata(code: str, ip: str = Depends(ip_limit["metadata"])):
    has, file_code = await get_code_file_by_code(code)
    if not has:
        ip_limit["metadata"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    ip_limit["metadata"].add_ip(ip)
    return APIResponse(detail=build_file_metadata(file_code))


@share_api.post("/metadata/")
async def post_file_metadata(
    data: SelectFileModel, ip: str = Depends(ip_limit["metadata"])
):
    has, file_code = await get_code_file_by_code(data.code)
    if not has:
        ip_limit["metadata"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    ip_limit["metadata"].add_ip(ip)
    return APIResponse(detail=build_file_metadata(file_code))


@share_api.get("/select/")
async def get_code_file(code: str, ip: str = Depends(ip_limit["error"])):
    has, file_code = await get_code_file_by_code(code)
    if not has:
        ip_limit["error"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    if not await consume_file_usage(file_code):
        return APIResponse(code=404, detail="文件已过期")
    if file_code.text is not None:
        filename = f"{file_code.prefix or 'Text'}{file_code.suffix or '.txt'}"
        return Response(
            content=file_code.text,
            media_type="text/plain",
            headers={
                "Content-Disposition": (
                    f"attachment; filename*=UTF-8''{quote(filename, safe='')}"
                )
            },
        )
    file_storage = await storage_for_share(file_code)
    return response_from_download(await file_storage.get_file_response(stored_file_of(file_code)))


@share_api.post("/select/")
async def select_file(data: SelectFileModel, ip: str = Depends(ip_limit["error"])):
    has, file_code = await get_code_file_by_code(data.code)
    if not has:
        ip_limit["error"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    file_storage = await storage_for_share(file_code)
    detail = await build_select_detail(file_code, file_storage)
    download_url = detail.get("download_url")
    consumes_on_download = isinstance(download_url, str) and download_url.startswith(
        "/share/download?"
    )
    if not consumes_on_download and not await consume_file_usage(file_code):
        return APIResponse(code=404, detail="文件已过期")
    if not consumes_on_download:
        detail.update(build_file_metadata(file_code))
    return APIResponse(detail=detail)


@share_api.get("/download")
async def download_file(key: str, code: str, ip: str = Depends(ip_limit["error"])):
    normalized_code = normalize_share_code(code)
    # 同时接受当前窗口与上一窗口 token，避免时间窗边界竞态导致偶发 403
    valid_keys = {
        await get_select_token(normalized_code, offset=0),
        await get_select_token(normalized_code, offset=1),
    }
    if key not in valid_keys:
        ip_limit["error"].add_ip(ip)
        raise HTTPException(status_code=403, detail="下载鉴权失败")
    has, file_code = await get_code_file_by_code(normalized_code)
    if not has:
        return APIResponse(code=404, detail=file_code)
    assert isinstance(file_code, FileCodes)
    if not await consume_file_usage(file_code):
        return APIResponse(code=404, detail="文件已过期")
    file_storage = await storage_for_share(file_code)
    return (
        APIResponse(detail=file_code.text)
        if file_code.text
        else response_from_download(await file_storage.get_file_response(stored_file_of(file_code)))
    )


chunk_api = APIRouter(prefix="/chunk", tags=["切片"])


async def parse_body_model(request: Request, model_class: type[BaseModel]):
    content_type = request.headers.get("content-type", "").lower()
    try:
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            payload = dict(await request.form())
        else:
            payload = await request.json()
        return model_class.model_validate(payload)
    except ValidationError as e:
        raise HTTPException(status_code=422, detail=e.errors())
    except Exception:
        raise HTTPException(status_code=400, detail="请求体格式错误")


async def parse_init_chunk_upload(request: Request) -> InitChunkUploadModel:
    return await parse_body_model(request, InitChunkUploadModel)


async def parse_complete_upload(request: Request) -> CompleteUploadModel:
    return await parse_body_model(request, CompleteUploadModel)


@chunk_api.post("/upload/init/", dependencies=[Depends(authorize_upload)])
async def init_chunk_upload(data: InitChunkUploadModel = Depends(parse_init_chunk_upload), access: Annotated[UploadAccess, Depends(authorize_upload)] = None):
    # 保持服务函数可被内部调用；HTTP 请求始终由依赖提供校验后的授权。
    access = access or UploadAccess()
    safe_file_name = await sanitize_filename(unquote(data.file_name or ""))
    validate_file_type(safe_file_name)
    # 使用文件真实声明大小校验上限，最后一个分片通常小于整片大小。
    total_chunks = (data.file_size + data.chunk_size - 1) // data.chunk_size
    if data.file_size > settings.upload_size:
        max_size_mb = settings.upload_size / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"文件大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    # 断点续传按寄件码隔离；普通上传不能恢复凭码创建的会话。
    if access.code_id is not None:
        tokens = await DeliveryFile.filter(delivery_id=access.code_id, status="pending").values_list("token", flat=True)
        session_scope = UploadChunk.filter(upload_id__in=tokens)
    else:
        session_scope = UploadChunk.exclude(upload_id__startswith="d_")
    existing_session = await session_scope.filter(
        chunk_hash=data.file_hash,
        chunk_index=-1,
        file_size=data.file_size,
        file_name=safe_file_name,
    ).first()

    if existing_session:
        if access.code_id is not None:
            access.record = await DeliveryFile.get(token=existing_session.upload_id)
        if not existing_session.save_path:
            await abort_access(access)
            await UploadChunk.filter(upload_id=existing_session.upload_id).delete()
            await release_storage(f"chunk:{existing_session.upload_id}")
        else:
            await reserve_storage(
                f"chunk:{existing_session.upload_id}",
                existing_session.file_size,
                ttl_seconds=max(
                    1, int(getattr(settings, "chunk_expire_hours", 24))
                )
                * 3600,
            )
            uploaded_chunks = await UploadChunk.filter(
                upload_id=existing_session.upload_id, completed=True
            ).values_list("chunk_index", flat=True)
            return APIResponse(
                detail={
                    "existed": False,
                    "upload_id": existing_session.upload_id,
                    "chunk_size": existing_session.chunk_size,
                    "total_chunks": existing_session.total_chunks,
                    "uploaded_chunks": list(uploaded_chunks),
                }
            )

    # 创建新的上传会话
    upload_id = uuid.uuid4().hex
    upload_id, delivery_path = await prepare_upload(access, safe_file_name, data.file_size, upload_id)
    reservation_token = f"chunk:{upload_id}"
    chunk_expire_seconds = max(1, int(getattr(settings, "chunk_expire_hours", 24))) * 3600
    await reserve_storage(
        reservation_token, data.file_size, ttl_seconds=chunk_expire_seconds
    )
    _, _, _, safe_file_name, save_path = await get_chunk_file_path_name(
        data.file_name, upload_id
    )
    try:
        await UploadChunk.create(
            upload_id=upload_id,
            chunk_index=-1,
            total_chunks=total_chunks,
            file_size=data.file_size,
            chunk_size=data.chunk_size,
            chunk_hash=data.file_hash,
            file_name=safe_file_name,
            save_path=delivery_path or save_path,
        )
    except Exception:
        await abort_access(access)
        await release_storage(reservation_token)
        raise
    return APIResponse(
        detail={
            "existed": False,
            "upload_id": upload_id,
            "chunk_size": data.chunk_size,
            "total_chunks": total_chunks,
            "uploaded_chunks": [],
        }
    )


@chunk_api.post(
    "/upload/chunk/{upload_id}/{chunk_index}",
    dependencies=[Depends(authorize_upload)],
)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    access: Annotated[UploadAccess, Depends(authorize_upload)] = None,
    chunk: UploadFile = File(...),
):
    # 已完成的寄件会话不能继续写分片，避免覆盖正在供下载的文件。
    if access is not None and access.record is not None and access.record.status != "pending":
        raise HTTPException(409, "上传已经完成")
    # 获取上传会话信息
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")
    await reserve_storage(
        f"chunk:{upload_id}",
        chunk_info.file_size,
        ttl_seconds=max(1, int(getattr(settings, "chunk_expire_hours", 24))) * 3600,
    )

    # 检查分片索引有效性
    if chunk_index < 0 or chunk_index >= chunk_info.total_chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="无效的分片索引")

    # 检查是否已上传（支持断点续传）
    existing_chunk = await UploadChunk.filter(
        upload_id=upload_id, chunk_index=chunk_index, completed=True
    ).first()
    if existing_chunk:
        return APIResponse(
            detail={"chunk_hash": existing_chunk.chunk_hash, "skipped": True}
        )

    # 读取分片数据并计算哈希
    chunk_data = await chunk.read()
    if chunk_index == 0:
        validate_header_bytes(chunk_info.file_name, None, chunk_data[:64])
    chunk_size = len(chunk_data)
    expected_size = min(chunk_info.chunk_size, chunk_info.file_size - chunk_index * chunk_info.chunk_size)
    if chunk_size != expected_size:
        raise HTTPException(400, "分片大小与声明的文件范围不一致")

    # 校验分片大小不超过声明的 chunk_size
    if chunk_size > chunk_info.chunk_size:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"分片大小超过声明值: 最大 {chunk_info.chunk_size}, 实际 {chunk_size}",
        )

    # 计算已上传分片数，校验累计大小不超限（用分片数 * chunk_size 估算）
    uploaded_count = await UploadChunk.filter(
        upload_id=upload_id, completed=True
    ).count()
    # 已上传分片的最大可能大小 + 当前分片
    max_uploaded_size = uploaded_count * chunk_info.chunk_size + chunk_size
    if max_uploaded_size > settings.upload_size:
        max_size_mb = settings.upload_size / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"累计上传大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    chunk_hash = hashlib.sha256(chunk_data).hexdigest()

    save_path = chunk_info.save_path

    # 保存分片到存储
    storage = await upload_storage(access)
    try:
        await storage.save_chunk(
            upload_id, chunk_index, chunk_data, chunk_hash, save_path
        )
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"分片保存失败: {str(e)}"
        )

    # 更新或创建分片记录（保存成功后再记录）
    await UploadChunk.update_or_create(
        upload_id=upload_id,
        chunk_index=chunk_index,
        defaults={
            "chunk_hash": chunk_hash,
            "completed": True,
            "file_size": chunk_info.file_size,
            "total_chunks": chunk_info.total_chunks,
            "chunk_size": chunk_info.chunk_size,
            "file_name": chunk_info.file_name,
            "save_path": chunk_info.save_path,
        },
    )
    return APIResponse(detail={"chunk_hash": chunk_hash})


@chunk_api.delete("/upload/{upload_id}", dependencies=[Depends(authorize_upload)])
async def cancel_upload(upload_id: str, access: Annotated[UploadAccess, Depends(authorize_upload)] = None):
    """取消上传并清理临时文件"""
    if access is not None and access.record is not None:
        await abort_access(access)
        return APIResponse(detail={"message": "上传已取消"})
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

    save_path = chunk_info.save_path

    # 清理存储中的临时文件
    storage = await upload_storage(access)
    if save_path:
        try:
            await storage.clean_chunks(upload_id, save_path)
        except Exception:
            logger.warning("取消分片上传：清理分片文件失败 upload_id=%s", upload_id, exc_info=True)

    # 清理数据库记录
    await UploadChunk.filter(upload_id=upload_id).delete()
    await release_storage(f"chunk:{upload_id}")

    return APIResponse(detail={"message": "上传已取消"})


@chunk_api.get(
    "/upload/status/{upload_id}", dependencies=[Depends(authorize_upload)]
)
async def get_upload_status(upload_id: str, access: Annotated[UploadAccess, Depends(authorize_upload)] = None):
    """获取上传状态"""
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

    # 获取已上传的分片列表
    uploaded_chunks = await UploadChunk.filter(
        upload_id=upload_id, completed=True
    ).values_list("chunk_index", flat=True)

    return APIResponse(
        detail={
            "upload_id": upload_id,
            "file_name": chunk_info.file_name,
            "file_size": chunk_info.file_size,
            "chunk_size": chunk_info.chunk_size,
            "total_chunks": chunk_info.total_chunks,
            "uploaded_chunks": list(uploaded_chunks),
            "progress": len(uploaded_chunks) / chunk_info.total_chunks * 100,
        }
    )


@chunk_api.post(
    "/upload/complete/{upload_id}", dependencies=[Depends(authorize_upload)]
)
async def complete_upload(
    upload_id: str,
    access: Annotated[UploadAccess, Depends(authorize_upload)] = None,
    data: CompleteUploadModel = Depends(parse_complete_upload),
    ip: str = Depends(ip_limit["upload"]),
):
    result = await completed_upload(access)
    if result:
        return APIResponse(detail=result)
    # 获取上传基本信息
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")
    validate_expire_style(data.expire_style)
    detail = await FileUploadService.complete_chunked_upload(
        upload_id, chunk_info, data.expire_value, data.expire_style, access=access
    )
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail=detail)


# ============ 预签名上传API ============
presign_api = APIRouter(prefix="/presign", tags=["预签名上传"])


def build_proxy_upload_urls(upload_id: str) -> dict:
    proxy_upload_url = f"/presign/upload/proxy/{upload_id}"
    return {
        "proxy_upload_url": proxy_upload_url,
        "legacy_proxy_upload_url": f"/api{proxy_upload_url}",
    }


async def _get_valid_session(
    upload_id: str, expected_mode: Optional[str] = None
) -> PresignUploadSession:
    """获取并验证会话"""
    session = await PresignUploadSession.filter(upload_id=upload_id).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")
    if await session.is_expired():
        await session.delete()
        await release_storage(f"presign:{upload_id}")
        raise HTTPException(404, "上传会话已过期")
    if expected_mode and session.mode != expected_mode:
        raise HTTPException(400, f"此会话不支持{expected_mode}模式")
    return session


@presign_api.post("/upload/init", dependencies=[Depends(authorize_upload)])
async def presign_upload_init(
    data: PresignUploadInitRequest, access: Annotated[UploadAccess, Depends(authorize_upload)] = None, ip: str = Depends(ip_limit["upload"])
):
    """初始化预签名上传，S3返回直传URL，其他存储返回代理URL"""
    validate_file_type(data.file_name)
    if data.file_size > settings.upload_size:
        raise HTTPException(
            403,
            f"文件大小超过限制，最大为 {settings.upload_size / (1024 * 1024):.2f} MB",
        )
    validate_expire_style(data.expire_style)

    upload_id = uuid.uuid4().hex
    upload_id, delivery_path = await prepare_upload(access, data.file_name, data.file_size, upload_id)
    reservation_token = f"presign:{upload_id}"
    await reserve_storage(
        reservation_token, data.file_size, ttl_seconds=PRESIGN_SESSION_EXPIRES
    )
    try:
        path, _, _, filename, save_path = await FileUploadService.generate_file_path(
            data.file_name, upload_id
        )
        if delivery_path:
            save_path = delivery_path
        storage: FileStorageInterface = await upload_storage(access)
        presigned_url = await storage.generate_presigned_upload_url(
            save_path, PRESIGN_SESSION_EXPIRES
        )
        mode = "direct" if presigned_url else "proxy"
        proxy_urls = build_proxy_upload_urls(upload_id)
        upload_url = presigned_url or proxy_urls["proxy_upload_url"]
        await PresignUploadSession.create(
            upload_id=upload_id,
            file_name=filename,
            file_size=data.file_size,
            save_path=save_path,
            mode=mode,
            expire_value=data.expire_value,
            expire_style=data.expire_style,
            expires_at=await get_now() + timedelta(seconds=PRESIGN_SESSION_EXPIRES),
        )
    except Exception:
        await abort_access(access)
        await release_storage(reservation_token)
        raise

    ip_limit["upload"].add_ip(ip)
    detail = {
        "upload_id": upload_id,
        "upload_url": upload_url,
        "mode": mode,
        "expires_in": PRESIGN_SESSION_EXPIRES,
    }
    if mode == "proxy":
        detail.update(proxy_urls)

    return APIResponse(
        detail=detail
    )


@presign_api.put(
    "/upload/proxy/{upload_id}", dependencies=[Depends(authorize_upload)]
)
async def presign_upload_proxy(
    upload_id: str, file: UploadFile = File(...), access: Annotated[UploadAccess, Depends(authorize_upload)] = None, ip: str = Depends(ip_limit["upload"])
):
    """代理模式上传，服务器转存到存储后端"""
    result = await completed_upload(access)
    if result:
        return APIResponse(detail=result)
    session = await _get_valid_session(upload_id, expected_mode="proxy")
    code = await FileUploadService.commit_proxy_upload(session, file, access=access)
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code, "name": session.file_name})


@presign_api.post(
    "/upload/confirm/{upload_id}", dependencies=[Depends(authorize_upload)]
)
async def presign_upload_confirm(upload_id: str, access: Annotated[UploadAccess, Depends(authorize_upload)] = None, ip: str = Depends(ip_limit["upload"])):
    """直传确认，客户端完成S3直传后调用获取分享码"""
    result = await completed_upload(access)
    if result:
        return APIResponse(detail=result)
    session = await _get_valid_session(upload_id, expected_mode="direct")
    code = await FileUploadService.confirm_direct_upload(session, access=access)
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code, "name": session.file_name})


@presign_api.get(
    "/upload/status/{upload_id}", dependencies=[Depends(authorize_upload)]
)
async def presign_upload_status(upload_id: str, access: Annotated[UploadAccess, Depends(authorize_upload)] = None):
    """查询上传会话状态"""
    session = await PresignUploadSession.filter(upload_id=upload_id).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")

    return APIResponse(
        detail={
            "upload_id": session.upload_id,
            "file_name": session.file_name,
            "file_size": session.file_size,
            "mode": session.mode,
            "created_at": session.created_at.isoformat(),
            "expires_at": session.expires_at.isoformat(),
            "is_expired": await session.is_expired(),
        }
    )


@presign_api.delete("/upload/{upload_id}", dependencies=[Depends(authorize_upload)])
async def presign_upload_cancel(upload_id: str, access: Annotated[UploadAccess, Depends(authorize_upload)] = None):
    """取消上传会话"""
    if access is not None and access.record is not None:
        await abort_access(access)
        return APIResponse(detail={"message": "上传会话已取消"})
    session = await PresignUploadSession.filter(upload_id=upload_id).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")

    if session.mode == "direct":
        storage: FileStorageInterface = await upload_storage(access)
        try:
            if await storage.file_exists(session.save_path):
                temp_file_code = StoredFile(
                    file_path=os.path.dirname(session.save_path),
                    uuid_file_name=os.path.basename(session.save_path),
                )
                await storage.delete_file(temp_file_code)
        except Exception:
            logger.warning("取消预签名会话：清理临时文件失败 upload_id=%s", upload_id, exc_info=True)

    await session.delete()
    await release_storage(f"presign:{upload_id}")
    return APIResponse(detail={"message": "上传会话已取消"})
