import hashlib
import uuid

from fastapi import APIRouter, Form, UploadFile, File, Depends, HTTPException
from starlette import status

from apps.admin.dependencies import share_required_login
from apps.base.models import FileCodes, UploadChunk
from apps.base.schemas import SelectFileModel, InitChunkUploadModel, CompleteUploadModel
from apps.base.utils import get_expire_info, get_file_path_name, ip_limit, get_chunk_file_path_name
from core.response import APIResponse
from core.settings import settings
from core.storage import storages, FileStorageInterface
from core.utils import get_select_token

share_api = APIRouter(prefix="/share", tags=["分享"])


async def validate_file_size(file: UploadFile, max_size: int) -> int:
    size = file.size
    if size is None:
        # 读取流计算大小，保持指针复位
        await file.seek(0, 2)
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
    expired_at, expired_count, used_count, code = await get_expire_info(expire_value, expire_style)
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


async def get_code_file_by_code(code, check=True):
    file_code = await FileCodes.filter(code=code).first()
    if not file_code:
        return False, "文件不存在"
    if await file_code.is_expired() and check:
        return False, "文件已过期"
    return True, file_code


async def update_file_usage(file_code):
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

    await update_file_usage(file_code)
    return await file_storage.get_file_response(file_code)


@share_api.post("/select/")
async def select_file(data: SelectFileModel, ip: str = Depends(ip_limit["error"])):
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    has, file_code = await get_code_file_by_code(data.code)
    if not has:
        ip_limit["error"].add_ip(ip)
        return APIResponse(code=404, detail=file_code)

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
            status_code=403,
            detail=f"文件大小超过限制，最大为 {max_size_mb:.2f} MB"
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
        # 复用已有会话，获取已上传的分片列表
        uploaded_chunks = await UploadChunk.filter(
            upload_id=existing_session.upload_id,
            completed=True
        ).values_list('chunk_index', flat=True)
        return APIResponse(detail={
            "existed": False,
            "upload_id": existing_session.upload_id,
            "chunk_size": existing_session.chunk_size,
            "total_chunks": existing_session.total_chunks,
            "uploaded_chunks": list(uploaded_chunks)
        })

    # 创建新的上传会话
    upload_id = uuid.uuid4().hex
    await UploadChunk.create(
        upload_id=upload_id,
        chunk_index=-1,
        total_chunks=total_chunks,
        file_size=data.file_size,
        chunk_size=data.chunk_size,
        chunk_hash=data.file_hash,
        file_name=data.file_name,
    )
    return APIResponse(detail={
        "existed": False,
        "upload_id": upload_id,
        "chunk_size": data.chunk_size,
        "total_chunks": total_chunks,
        "uploaded_chunks": []
    })


@chunk_api.post("/upload/chunk/{upload_id}/{chunk_index}", dependencies=[Depends(share_required_login)])
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
        upload_id=upload_id,
        chunk_index=chunk_index,
        completed=True
    ).first()
    if existing_chunk:
        return APIResponse(detail={"chunk_hash": existing_chunk.chunk_hash, "skipped": True})

    # 读取分片数据并计算哈希
    chunk_data = await chunk.read()
    chunk_size = len(chunk_data)

    # 校验分片大小不超过声明的 chunk_size
    if chunk_size > chunk_info.chunk_size:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            detail=f"分片大小超过声明值: 最大 {chunk_info.chunk_size}, 实际 {chunk_size}"
        )

    # 计算已上传分片数，校验累计大小不超限（用分片数 * chunk_size 估算）
    uploaded_count = await UploadChunk.filter(
        upload_id=upload_id,
        completed=True
    ).count()
    # 已上传分片的最大可能大小 + 当前分片
    max_uploaded_size = uploaded_count * chunk_info.chunk_size + chunk_size
    if max_uploaded_size > settings.uploadSize:
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise HTTPException(
            status_code=403,
            detail=f"累计上传大小超过限制，最大为 {max_size_mb:.2f} MB"
        )
    
    chunk_hash = hashlib.sha256(chunk_data).hexdigest()

    # 获取文件路径
    _, _, _, _, save_path = await get_chunk_file_path_name(chunk_info.file_name, upload_id)
    
    # 保存分片到存储
    storage = storages[settings.file_storage]()
    try:
        await storage.save_chunk(upload_id, chunk_index, chunk_data, chunk_hash, save_path)
    except Exception as e:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"分片保存失败: {str(e)}")
    
    # 更新或创建分片记录（保存成功后再记录）
    await UploadChunk.update_or_create(
        upload_id=upload_id,
        chunk_index=chunk_index,
        defaults={
            'chunk_hash': chunk_hash,
            'completed': True,
            'file_size': chunk_info.file_size,
            'total_chunks': chunk_info.total_chunks,
            'chunk_size': chunk_info.chunk_size,
            'file_name': chunk_info.file_name
        }
    )
    return APIResponse(detail={"chunk_hash": chunk_hash})


@chunk_api.delete("/upload/{upload_id}", dependencies=[Depends(share_required_login)])
async def cancel_upload(upload_id: str):
    """取消上传并清理临时文件"""
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")
    
    # 获取文件路径
    _, _, _, _, save_path = await get_chunk_file_path_name(chunk_info.file_name, upload_id)
    
    # 清理存储中的临时文件
    storage = storages[settings.file_storage]()
    try:
        await storage.clean_chunks(upload_id, save_path)
    except Exception as e:
        # 记录错误但不阻止删除数据库记录
        pass
    
    # 清理数据库记录
    await UploadChunk.filter(upload_id=upload_id).delete()
    
    return APIResponse(detail={"message": "上传已取消"})


@chunk_api.get("/upload/status/{upload_id}", dependencies=[Depends(share_required_login)])
async def get_upload_status(upload_id: str):
    """获取上传状态"""
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")
    
    # 获取已上传的分片列表
    uploaded_chunks = await UploadChunk.filter(
        upload_id=upload_id,
        completed=True
    ).values_list('chunk_index', flat=True)
    
    return APIResponse(detail={
        "upload_id": upload_id,
        "file_name": chunk_info.file_name,
        "file_size": chunk_info.file_size,
        "chunk_size": chunk_info.chunk_size,
        "total_chunks": chunk_info.total_chunks,
        "uploaded_chunks": list(uploaded_chunks),
        "progress": len(uploaded_chunks) / chunk_info.total_chunks * 100
    })


@chunk_api.post("/upload/complete/{upload_id}", dependencies=[Depends(share_required_login)])
async def complete_upload(upload_id: str, data: CompleteUploadModel, ip: str = Depends(ip_limit["upload"])):
    # 获取上传基本信息
    chunk_info = await UploadChunk.filter(upload_id=upload_id, chunk_index=-1).first()
    if not chunk_info:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="上传会话不存在")

    storage = storages[settings.file_storage]()
    # 验证所有分片
    completed_chunks_list = await UploadChunk.filter(
        upload_id=upload_id,
        completed=True
    ).all()
    if len(completed_chunks_list) != chunk_info.total_chunks:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="分片不完整")

    # 用分片数 * chunk_size 校验最大可能大小
    max_total_size = len(completed_chunks_list) * chunk_info.chunk_size
    if max_total_size > settings.uploadSize:
        # 清理已上传的分片
        _, _, _, _, save_path = await get_chunk_file_path_name(chunk_info.file_name, upload_id)
        try:
            await storage.clean_chunks(upload_id, save_path)
        except Exception:
            pass
        await UploadChunk.filter(upload_id=upload_id).delete()
        max_size_mb = settings.uploadSize / (1024 * 1024)
        raise HTTPException(
            status_code=403,
            detail=f"实际上传大小超过限制，最大为 {max_size_mb:.2f} MB"
        )

    # 获取文件路径
    path, suffix, prefix, _, save_path = await get_chunk_file_path_name(chunk_info.file_name, upload_id)
    
    try:
        # 合并文件并计算哈希
        _, file_hash = await storage.merge_chunks(upload_id, chunk_info, save_path)
        # 创建文件记录
        expired_at, expired_count, used_count, code = await get_expire_info(data.expire_value, data.expire_style)
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
            suffix=suffix
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
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"文件合并失败: {str(e)}")
