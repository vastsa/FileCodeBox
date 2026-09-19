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
from apps.base.services import stored_file_of
from apps.base.share_storage import remove_delivery_share, storage_for_share
from apps.base.local_share import should_skip_storage_delete
from core.utils import get_now

async def delete_expire_files():
    while True:
        try:
            await refresh_settings()
            # 遍历 share目录下的所有文件夹，删除空的文件夹，并判断父目录是否为空，如果为空也删除
            if settings.file_storage == "local":
                for root, dirs, files in os.walk(f"{data_root}/share/data"):
                    if not dirs and not files:
                        os.rmdir(root)
            await ip_limit["error"].remove_expired_ip()
            await ip_limit["metadata"].remove_expired_ip()
            await ip_limit["upload"].remove_expired_ip()
            await StorageReservation.filter(expires_at__lte=await get_now()).delete()
            expire_data = await FileCodes.filter(
                Q(expired_at__lt=await get_now()) | Q(expired_count=0)
            ).all()
            for exp in expire_data:
                try:
                    if await remove_delivery_share(exp):
                        continue
                except Exception:
                    # 关联清理事务失败时保留分享，下一轮重试，不能落入普通删除分支丢失关联。
                    logger.warning("寄件分享过期清理失败 id=%s", exp.id, exc_info=True)
                    continue
                try:
                    # 文本内容只在数据库中；NAS 引用不删原文件，其他文件按存储快照清理。
                    if not should_skip_storage_delete(exp):
                        await (await storage_for_share(exp)).delete_file(stored_file_of(exp))
                except Exception as e:
                    logger.error(f"删除过期文件失败 code={exp.code}: {e}")
                    # 文件定位或后端异常时保留记录，下一轮按同一快照重试。
                    continue
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
            expire_hours = getattr(settings, "chunk_expire_hours", 24)
            now = await get_now()
            expire_time = now - datetime.timedelta(hours=expire_hours)
            expired_sessions = await UploadChunk.filter(
                chunk_index=-1, created_at__lt=expire_time
            ).exclude(upload_id__startswith="d_").all()

            for session in expired_sessions:
                try:
                    save_path = session.save_path
                    if not save_path:
                        _, _, _, _, save_path = await get_chunk_file_path_name(
                            session.file_name, session.upload_id
                        )
                    storage = storages[session.storage_type or settings.file_storage]()
                    await storage.clean_chunks(session.upload_id, save_path)
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
            now = await get_now()
            expired_sessions = await PresignUploadSession.filter(
                expires_at__lt=now
            ).exclude(upload_id__startswith="d_").all()
            for session in expired_sessions:
                if session.mode == "direct":
                    try:
                        storage = storages[session.storage_type or settings.file_storage]()
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
                await StorageReservation.filter(
                    token=f"presign:{session.upload_id}"
                ).delete()
                await session.delete()
        except Exception as e:
            logger.error(f"清理过期预签名会话异常: {e}")
        finally:
            await asyncio.sleep(900)
