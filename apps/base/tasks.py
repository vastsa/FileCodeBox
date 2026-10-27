# @Time    : 2023/8/15 22:00
# @Author  : Lan
# @File    : tasks.py
# @Software: PyCharm
import asyncio
import datetime
import os

from tortoise.expressions import Q

from apps.base.models import (
    FileCodes,
    PresignUploadSession,
    StorageReservation,
    UploadChunk,
)
from apps.base.utils import ip_limit, get_chunk_file_path_name
from apps.base.config import refresh_settings
from core.logger import logger
from core.settings import settings, data_root
from core.storage import FileStorageInterface, StoredFile, storages
from apps.base.local_share import is_local_ref
from core.utils import get_now

# 清理任务单批处理量：限制单次 ORM 实例数量与 text 大字段峰值。
CLEANUP_BATCH_SIZE = 200


def _prune_empty_share_dirs(root: str) -> None:
    """删除 share/data 下的空目录（阻塞操作，调用方需放入线程池）。"""
    for current, dirs, files in os.walk(os.path.join(str(root), "share", "data")):
        if not dirs and not files:
            os.rmdir(current)


async def delete_expire_files():
    while True:
        try:
            await refresh_settings()
            file_storage: FileStorageInterface = storages[settings.file_storage]()
            # 遍历 share目录下的所有文件夹，删除空的文件夹，并判断父目录是否为空，如果为空也删除
            # 目录遍历是阻塞的文件系统调用，下放线程池避免卡住事件循环
            if settings.file_storage == "local":
                await asyncio.to_thread(_prune_empty_share_dirs, data_root)
            await ip_limit["error"].remove_expired_ip()
            await ip_limit["metadata"].remove_expired_ip()
            await ip_limit["upload"].remove_expired_ip()
            now = await get_now()
            await StorageReservation.filter(expires_at__lte=now).delete()
            # 游标分批：只取必要字段（不含 text），避免一次性载入全部过期记录；
            # 用 id 游标而非纯 limit，单条删除失败时也不会在同一批里反复重试卡死。
            last_id = 0
            while True:
                expire_data = await FileCodes.filter(
                    (Q(expired_at__lt=now) | Q(expired_count=0)) & Q(id__gt=last_id)
                ).only(
                    "id", "code", "prefix", "suffix", "file_path", "uuid_file_name"
                ).order_by("id").limit(CLEANUP_BATCH_SIZE)
                if not expire_data:
                    break
                for exp in expire_data:
                    last_id = exp.id
                    try:
                        if not is_local_ref(exp):
                            # 删除只需要路径字段；不加载 text 大字段
                            await file_storage.delete_file(
                                StoredFile(
                                    file_path=exp.file_path,
                                    uuid_file_name=exp.uuid_file_name,
                                    code=exp.code,
                                    prefix=exp.prefix,
                                    suffix=exp.suffix,
                                )
                            )
                    except Exception as e:
                        logger.error(f"删除过期文件失败 code={exp.code}: {e}")
                    try:
                        await exp.delete()
                    except Exception as e:
                        logger.error(f"删除记录失败 code={exp.code}: {e}")
        except Exception as e:
            logger.error(e)
        finally:
            await asyncio.sleep(600)


async def clean_incomplete_uploads():
    while True:
        try:
            await refresh_settings()
            file_storage: FileStorageInterface = storages[settings.file_storage]()
            expire_hours = getattr(settings, "chunk_expire_hours", 24)
            now = await get_now()
            expire_time = now - datetime.timedelta(hours=expire_hours)
            last_id = 0
            while True:
                expired_sessions = await UploadChunk.filter(
                    chunk_index=-1,
                    created_at__lt=expire_time,
                    id__gt=last_id,
                ).only("id", "upload_id", "save_path", "file_name").order_by(
                    "id"
                ).limit(CLEANUP_BATCH_SIZE)
                if not expired_sessions:
                    break
                for session in expired_sessions:
                    last_id = session.id
                    try:
                        save_path = session.save_path
                        if not save_path:
                            _, _, _, _, save_path = await get_chunk_file_path_name(
                                session.file_name, session.upload_id
                            )
                        await file_storage.clean_chunks(session.upload_id, save_path)
                    except Exception as e:
                        logger.error(
                            f"清理分片文件失败 upload_id={session.upload_id}: {e}"
                        )

                    try:
                        await UploadChunk.filter(upload_id=session.upload_id).delete()
                        await StorageReservation.filter(
                            token=f"chunk:{session.upload_id}"
                        ).delete()
                        logger.info(f"已清理过期上传会话 upload_id={session.upload_id}")
                    except Exception as e:
                        logger.error(
                            f"删除分片记录失败 upload_id={session.upload_id}: {e}"
                        )

        except Exception as e:
            logger.error(f"清理未完成上传任务异常: {e}")
        finally:
            await asyncio.sleep(3600)


async def clean_expired_presign_sessions():
    while True:
        try:
            await refresh_settings()
            storage: FileStorageInterface = storages[settings.file_storage]()
            now = await get_now()
            last_id = 0
            while True:
                expired_sessions = await PresignUploadSession.filter(
                    expires_at__lt=now, id__gt=last_id
                ).only("id", "upload_id", "mode", "save_path").order_by(
                    "id"
                ).limit(CLEANUP_BATCH_SIZE)
                if not expired_sessions:
                    break
                for session in expired_sessions:
                    last_id = session.id
                    if session.mode == "direct":
                        try:
                            if await storage.file_exists(session.save_path):
                                await storage.delete_file(
                                    StoredFile(
                                        file_path=os.path.dirname(session.save_path),
                                        uuid_file_name=os.path.basename(session.save_path),
                                    )
                                )
                        except Exception as e:
                            logger.error(
                                "清理过期直传文件失败 "
                                f"upload_id={session.upload_id}: {e}"
                            )
                    try:
                        await StorageReservation.filter(
                            token=f"presign:{session.upload_id}"
                        ).delete()
                        await session.delete()
                    except Exception as e:
                        logger.error(
                            "删除过期预签名会话记录失败 "
                            f"upload_id={session.upload_id}: {e}"
                        )
        except Exception as e:
            logger.error(f"清理过期预签名会话异常: {e}")
        finally:
            await asyncio.sleep(900)
