import datetime
import hashlib
import os
import uuid
from datetime import timedelta
from urllib.parse import unquote

from typing import Optional, Tuple, Union

from fastapi import APIRouter, Form, UploadFile, File, Depends, HTTPException
from starlette import status

from apps.admin.dependencies import share_required_login
from apps.base.models import FileCodes, UploadChunk, PresignUploadSession
from apps.base.schemas import (
    SelectFileModel,
    InitChunkUploadModel,
    CompleteUploadModel,
    PresignUploadInitRequest,
)
from apps.base.utils import (
    get_expire_info,
    get_file_path_name,
    ip_limit,
    get_chunk_file_path_name,
)
from core.response import APIResponse
from core.settings import settings
from core.storage import storages, FileStorageInterface
from core.utils import get_select_token, get_now, sanitize_filename

share_api = APIRouter(prefix="/share", tags=["分享"])


# ============ 公共服务层 ============
class FileUploadService:
    """统一的文件上传服务"""

    @staticmethod
    async def generate_file_path(
        file_name: str, upload_id: Optional[str] = None
    ) -> tuple[str, str, str, str, str]:
        """统一的路径生成"""
        today = datetime.datetime.now()
        storage_path = settings.storage_path.strip("/")
        file_uuid = upload_id or uuid.uuid4().hex
        filename = await sanitize_filename(unquote(file_name))
        base_path = f"share/data/{today.strftime('%Y/%m/%d')}/{file_uuid}"
        path = f"{storage_path}/{base_path}" if storage_path else base_path
        prefix, suffix = os.path.splitext(filename)
        save_path = f"{path}/{filename}"
        return path, suffix, prefix, filename, save_path

    @staticmethod
    async def create_file_record(
        file_name: str,
        file_size: int,
        file_path: str,
        expire_value: int,
        expire_style: str,
        **extra_fields,
    ) -> str:
        """统一创建FileCodes记录，返回code"""
        expired_at, expired_count, used_count, code = await get_expire_info(
            expire_value, expire_style
        )
        prefix, suffix = os.path.splitext(file_name)

        await FileCodes.create(
            code=code,
            prefix=prefix,
            suffix=suffix,
            uuid_file_name=file_name,
            file_path=file_path,
            size=file_size,
            expired_at=expired_at,
            expired_count=expired_count,
            used_count=used_count,
            **extra_fields,
        )
        return code


async def validate_file_size(file: UploadFile, max_size: int) -> int:
    size = file.size
    if size is None:
        await file.seek(0, 2)  # type: ignore[arg-type]
        size = file.file.tell()
        await file.seek(0)
    if size > max_size:
        max_size_mb = max_size / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"大小超过限制,最大为{max_size_mb:.2f} MB"
        )
    return size


async def create_file_code(code, **kwargs):
    return await FileCodes.create(code=code, **kwargs)


@share_api.post("/text/", dependencies=[Depends(share_required_login)])
async def share_text(
    text: str = Form(...),
    expire_value: int = Form(default=1, gt=0),
    expire_style: str = Form(default="day"),
    ip: str = Depends(ip_limit["upload"]),
):
    text_size = len(text.encode("utf-8"))
    max_txt_size = 222 * 1024
    if text_size > max_txt_size:
        raise HTTPException(status_code=403, detail="内容过多,建议采用文件形式")

    expired_at, expired_count, used_count, code = await get_expire_info(
        expire_value, expire_style
    )
    await create_file_code(
        code=code,
        text=text,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
        size=len(text),
        prefix="Text",
    )
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code})


@share_api.post("/file/", dependencies=[Depends(share_required_login)])
async def share_file(
    expire_value: int = Form(default=1, gt=0),
    expire_style: str = Form(default="day"),
    file: UploadFile = File(...),
    ip: str = Depends(ip_limit["upload"]),
):
    file_size = await validate_file_size(file, settings.uploadSize)
    if expire_style not in settings.expireStyle:
        raise HTTPException(status_code=400, detail="过期时间类型错误")
    expired_at, expired_count, used_count, code = await get_expire_info(
        expire_value, expire_style
    )
    path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(file)
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    await file_storage.save_file(file, save_path)
    await create_file_code(
        code=code,
        prefix=prefix,
        suffix=suffix,
        uuid_file_name=uuid_file_name,
        file_path=path,
        size=file_size,
        expired_at=expired_at,
        expired_count=expired_count,
        used_count=used_count,
    )
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code, "name": file.filename})


async def get_code_file_by_code(
    code: str, check: bool = True
) -> Tuple[bool, Union[FileCodes, str]]:
    file_code = await FileCodes.filter(code=code).first()
    if not file_code:
        return False, "文件不存在"
    if await file_code.is_expired() and check:
        return False, "文件已过期"
    return True, file_code


async def update_file_usage(file_code: FileCodes) -> None:
    file_code.used_count += 1
    if file_code.expired_count > 0:
        file_code.expired_count -= 1
    await file_code.save()


@share_api.get("/select/")
async def get_code_file(code: str, ip: str = Depends(ip_limit["error"])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_code_file_by_code(code)
    if not has:
        ip_limit["error"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    await update_file_usage(file_code)
    return await file_storage.get_file_response(file_code)


@share_api.post("/select/")
async def select_file(data: SelectFileModel, ip: str = Depends(ip_limit["error"])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_code_file_by_code(data.code)
    if not has:
        ip_limit["error"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

    assert isinstance(file_code, FileCodes)
    await update_file_usage(file_code)
    return APIResponse(
        detail={
            "code": file_code.code,
            "name": file_code.prefix + file_code.suffix,
            "size": file_code.size,
            "text": (
                file_code.text
                if file_code.text is not None
                else await file_storage.get_file_url(file_code)
            ),
        }
    )


@share_api.get("/download")
async def download_file(key: str, code: str, ip: str = Depends(ip_limit["error"])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    if await get_select_token(code) != key:
        ip_limit["error"].add_ip(ip)
        raise HTTPException(status_code=403, detail="下载鉴权失败")
    has, file_code = await get_code_file_by_code(code, False)
    if not has:
        return APIResponse(code=404, detail="文件不存在")
    assert isinstance(file_code, FileCodes)
    return (
        APIResponse(detail=file_code.text)
        if file_code.text
        else await file_storage.get_file_response(file_code)
    )


chunk_api = APIRouter(prefix="/chunk", tags=["切片"])


@chunk_api.post("/upload/init/", dependencies=[Depends(share_required_login)])
async def init_chunk_upload(data: InitChunkUploadModel):
    # 服务端校验：根据 total_chunks * chunk_size 计算理论最大上传量
    total_chunks = (data.file_size + data.chunk_size - 1) // data.chunk_size
    max_possible_size = total_chunks * data.chunk_size
    if max_possible_size > settings.uploadSize:
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"文件大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    # # 秒传检查
    # existing = await FileCodes.filter(file_hash=data.file_hash).first()
    # if existing:
    #     if await existing.is_expired():
    #         file_storage: FileStorageInterface = storages[settings.file_storage](
    #         )
    #         await file_storage.delete_file(existing)
    #         await existing.delete()
    #     else:
    #         return APIResponse(detail={
    #             "code": existing.code,
    #             "existed": True,
    #             "name": f'{existing.prefix}{existing.suffix}'
    #         })

    # 断点续传：检查是否存在相同文件的未完成上传会话
    existing_session = await UploadChunk.filter(
        chunk_hash=data.file_hash,
        chunk_index=-1,
        file_size=data.file_size,
        file_name=data.file_name,
    ).first()

    if existing_session:
        if not existing_session.save_path:
            await UploadChunk.filter(upload_id=existing_session.upload_id).delete()
        else:
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
    _, _, _, _, save_path = await get_chunk_file_path_name(data.file_name, upload_id)
    await UploadChunk.create(
        upload_id=upload_id,
        chunk_index=-1,
        total_chunks=total_chunks,
        file_size=data.file_size,
        chunk_size=data.chunk_size,
        chunk_hash=data.file_hash,
        file_name=data.file_name,
        save_path=save_path,
    )
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
    dependencies=[Depends(share_required_login)],
)
async def upload_chunk(
    upload_id: str,
    chunk_index: int,
    chunk: UploadFile = File(...),
):
    # 获取上传会话信息
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

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
    chunk_size = len(chunk_data)

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
    if max_uploaded_size > settings.uploadSize:
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"累计上传大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    chunk_hash = hashlib.sha256(chunk_data).hexdigest()

    save_path = chunk_info.save_path

    # 保存分片到存储
    storage = storages[settings.file_storage]()
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


@chunk_api.delete("/upload/{upload_id}", dependencies=[Depends(share_required_login)])
async def cancel_upload(upload_id: str):
    """取消上传并清理临时文件"""
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

    save_path = chunk_info.save_path

    # 清理存储中的临时文件
    storage = storages[settings.file_storage]()
    if save_path:
        try:
            await storage.clean_chunks(upload_id, save_path)
        except Exception as e:
            pass

    # 清理数据库记录
    await UploadChunk.filter(upload_id=upload_id).delete()

    return APIResponse(detail={"message": "上传已取消"})


@chunk_api.get(
    "/upload/status/{upload_id}", dependencies=[Depends(share_required_login)]
)
async def get_upload_status(upload_id: str):
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
    "/upload/complete/{upload_id}", dependencies=[Depends(share_required_login)]
)
async def complete_upload(
    upload_id: str, data: CompleteUploadModel, ip: str = Depends(ip_limit["upload"])
):
    # 获取上传基本信息
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

    storage = storages[settings.file_storage]()
    # 验证所有分片
    completed_chunks_list = await UploadChunk.filter(
        upload_id=upload_id, completed=True
    ).all()
    if len(completed_chunks_list) != chunk_info.total_chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="分片不完整")

    # 用分片数 * chunk_size 校验最大可能大小
    max_total_size = len(completed_chunks_list) * chunk_info.chunk_size
    if max_total_size > settings.uploadSize:
        save_path = chunk_info.save_path
        if save_path:
            try:
                await storage.clean_chunks(upload_id, save_path)
            except Exception:
                pass
        await UploadChunk.filter(upload_id=upload_id).delete()
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise HTTPException(
            status_code=403, detail=f"实际上传大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    save_path = chunk_info.save_path
    path = os.path.dirname(save_path) if save_path else ""
    prefix, suffix = os.path.splitext(chunk_info.file_name)

    try:
        # 合并文件并计算哈希
        _, file_hash = await storage.merge_chunks(upload_id, chunk_info, save_path)
        # 创建文件记录
        expired_at, expired_count, used_count, code = await get_expire_info(
            data.expire_value, data.expire_style
        )
        await FileCodes.create(
            code=code,
            file_hash=file_hash,  # 使用合并后计算的哈希
            is_chunked=True,
            upload_id=upload_id,
            size=chunk_info.file_size,
            expired_at=expired_at,
            expired_count=expired_count,
            used_count=used_count,
            file_path=path,
            uuid_file_name=f"{prefix}{suffix}",
            prefix=prefix,
            suffix=suffix,
        )
        # 清理临时文件
        await storage.clean_chunks(upload_id, save_path)
        # 清理数据库中的分片记录
        await UploadChunk.filter(upload_id=upload_id).delete()
        ip_limit["upload"].add_ip(ip)
        return APIResponse(detail={"code": code, "name": chunk_info.file_name})
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail=str(e))
    except Exception as e:
        # 合并失败时清理临时文件
        try:
            await storage.clean_chunks(upload_id, save_path)
        except Exception:
            pass
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件合并失败: {str(e)}"
        )


# ============ 预签名上传API ============
presign_api = APIRouter(prefix="/presign", tags=["预签名上传"])

PRESIGN_SESSION_EXPIRES = 900  # 15分钟


async def _get_valid_session(
    upload_id: str, expected_mode: Optional[str] = None
) -> PresignUploadSession:
    """获取并验证会话"""
    session = await PresignUploadSession.filter(upload_id=upload_id).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")
    if await session.is_expired():
        await session.delete()
        raise HTTPException(404, "上传会话已过期")
    if expected_mode and session.mode != expected_mode:
        raise HTTPException(400, f"此会话不支持{expected_mode}模式")
    return session


@presign_api.post("/upload/init", dependencies=[Depends(share_required_login)])
async def presign_upload_init(
    data: PresignUploadInitRequest, ip: str = Depends(ip_limit["upload"])
):
    """初始化预签名上传，S3返回直传URL，其他存储返回代理URL"""
    if data.file_size > settings.uploadSize:
        raise HTTPException(
            403,
            f"文件大小超过限制，最大为 {settings.uploadSize / (1024 * 1024):.2f} MB",
        )
    if data.expire_style not in settings.expireStyle:
        raise HTTPException(400, "过期时间类型错误")

    upload_id = uuid.uuid4().hex
    path, _, _, filename, save_path = await FileUploadService.generate_file_path(
        data.file_name, upload_id
    )

    storage: FileStorageInterface = storages[settings.file_storage]()
    presigned_url = await storage.generate_presigned_upload_url(
        save_path, PRESIGN_SESSION_EXPIRES
    )

    mode = "direct" if presigned_url else "proxy"
    upload_url = presigned_url or f"/api/presign/upload/proxy/{upload_id}"

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

    ip_limit["upload"].add_ip(ip)
    return APIResponse(
        detail={
            "upload_id": upload_id,
            "upload_url": upload_url,
            "mode": mode,
            "expires_in": PRESIGN_SESSION_EXPIRES,
        }
    )


@presign_api.put(
    "/upload/proxy/{upload_id}", dependencies=[Depends(share_required_login)]
)
async def presign_upload_proxy(
    upload_id: str, file: UploadFile = File(...), ip: str = Depends(ip_limit["upload"])
):
    """代理模式上传，服务器转存到存储后端"""
    session = await _get_valid_session(upload_id, expected_mode="proxy")

    file_size = await validate_file_size(file, settings.uploadSize)
    if abs(file_size - session.file_size) > 1024:
        raise HTTPException(400, "文件大小与声明不符")

    storage: FileStorageInterface = storages[settings.file_storage]()
    try:
        await storage.save_file(file, session.save_path)
    except Exception as e:
        raise HTTPException(500, f"文件保存失败: {str(e)}")

    code = await FileUploadService.create_file_record(
        session.file_name,
        file_size,
        os.path.dirname(session.save_path),
        session.expire_value,
        session.expire_style,
    )

    await session.delete()
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code, "name": session.file_name})


@presign_api.post(
    "/upload/confirm/{upload_id}", dependencies=[Depends(share_required_login)]
)
async def presign_upload_confirm(upload_id: str, ip: str = Depends(ip_limit["upload"])):
    """直传确认，客户端完成S3直传后调用获取分享码"""
    session = await _get_valid_session(upload_id, expected_mode="direct")

    storage: FileStorageInterface = storages[settings.file_storage]()
    if not await storage.file_exists(session.save_path):
        raise HTTPException(404, "文件未上传或上传失败")

    code = await FileUploadService.create_file_record(
        session.file_name,
        session.file_size,
        os.path.dirname(session.save_path),
        session.expire_value,
        session.expire_style,
    )

    await session.delete()
    ip_limit["upload"].add_ip(ip)
    return APIResponse(detail={"code": code, "name": session.file_name})


@presign_api.get(
    "/upload/status/{upload_id}", dependencies=[Depends(share_required_login)]
)
async def presign_upload_status(upload_id: str):
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


@presign_api.delete("/upload/{upload_id}", dependencies=[Depends(share_required_login)])
async def presign_upload_cancel(upload_id: str):
    """取消上传会话"""
    session = await PresignUploadSession.filter(upload_id=upload_id).first()
    if not session:
        raise HTTPException(404, "上传会话不存在")

    if session.mode == "direct":
        storage: FileStorageInterface = storages[settings.file_storage]()
        try:
            if await storage.file_exists(session.save_path):
                temp_file_code = FileCodes(
                    file_path=os.path.dirname(session.save_path),
                    uuid_file_name=os.path.basename(session.save_path),
                )
                await storage.delete_file(temp_file_code)
        except Exception:
            pass

    await session.delete()
    return APIResponse(detail={"message": "上传会话已取消"})
