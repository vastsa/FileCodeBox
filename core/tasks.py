# @Time    : 2023/8/15 22:00
# @Author  : Lan
# @File    : tasks.py
# @Software: PyCharm
import asyncio
import datetime
import logging
import os

from tortoise.expressions import Q

from apps.base.models import FileCodes, UploadChunk
from apps.base.utils import ip_limit, get_chunk_file_path_name
from core.settings import settings, data_root
from core.storage import FileStorageInterface, storages
from core.utils import get_now


async def delete_expire_files():
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    while True:
        try:
            # 遍历 share目录下的所有文件夹，删除空的文件夹，并判断父目录是否为空，如果为空也删除
            if settings.file_storage == "local":
                for root, dirs, files in os.walk(f"{data_root}/share/data"):
                    if not dirs and not files:
                        os.rmdir(root)
            await ip_limit["error"].remove_expired_ip()
            await ip_limit["upload"].remove_expired_ip()
            expire_data = await FileCodes.filter(
                Q(expired_at__lt=await get_now()) | Q(expired_count=0)
            ).all()
            for exp in expire_data:
                try:
                    await file_storage.delete_file(exp)
                except Exception as e:
                    logging.error(f"删除过期文件失败 code={exp.code}: {e}")
                try:
                    await exp.delete()
                except Exception as e:
                    logging.error(f"删除记录失败 code={exp.code}: {e}")
        except Exception as e:
            logging.error(e)
        finally:
            await asyncio.sleep(600)


async def clean_incomplete_uploads():
    """清理超时未完成的分片上传"""
    file_storage: FileStorageInterface = storages[settings.file_storage]()
    # 默认 24 小时未完成的上传视为过期
    expire_hours = getattr(settings, 'chunk_expire_hours', 24)

    while True:
        try:
            expire_time = datetime.datetime.now() - datetime.timedelta(hours=expire_hours)
            # 查找所有过期的上传会话（chunk_index=-1 的记录）
            expired_sessions = await UploadChunk.filter(
                chunk_index=-1,
                created_at__lt=expire_time
            ).all()

            for session in expired_sessions:
                try:
                    # 获取分片存储路径
                    _, _, _, _, save_path = await get_chunk_file_path_name(
                        session.file_name, session.upload_id
                    )
                    # 清理存储中的临时文件
                    await file_storage.clean_chunks(session.upload_id, save_path)
                except Exception as e:
                    logging.error(f"清理分片文件失败 upload_id={session.upload_id}: {e}")

                try:
                    # 删除该会话的所有数据库记录
                    await UploadChunk.filter(upload_id=session.upload_id).delete()
                    logging.info(f"已清理过期上传会话 upload_id={session.upload_id}")
                except Exception as e:
                    logging.error(f"删除分片记录失败 upload_id={session.upload_id}: {e}")

        except Exception as e:
            logging.error(f"清理未完成上传任务异常: {e}")
        finally:
            await asyncio.sleep(3600)  # 每小时执行一次
