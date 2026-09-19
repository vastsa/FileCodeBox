from botocore.exceptions import ClientError
import hashlib
from core.logger import logger
from typing import BinaryIO, Optional

import aiohttp
import asyncio
from pathlib import Path
import aioboto3
from botocore.config import Config
from core.errors import StorageError
from core.settings import settings
from core.utils import get_file_url
from starlette.background import BackgroundTask

from core.storage._base import (
    FileStorageInterface,
    S3_MIN_MULTIPART_PART_SIZE,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)


class S3FileStorage(FileStorageInterface):
    def __init__(self):
        self.access_key_id = settings.s3_access_key_id
        self.secret_access_key = settings.s3_secret_access_key
        self.bucket_name = settings.s3_bucket_name
        self.s3_hostname = settings.s3_hostname
        self.region_name = settings.s3_region_name
        self.signature_version = settings.s3_signature_version
        self.endpoint_url = settings.s3_endpoint_url or f"https://{self.s3_hostname}"
        self.aws_session_token = settings.aws_session_token
        self.addressing_style = str(settings.s3_addressing_style or "auto").lower()
        self.proxy = settings.s3_proxy
        self.session = aioboto3.Session(
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
        )
        if not settings.s3_endpoint_url:
            self.endpoint_url = f"https://{self.s3_hostname}"
        else:
            # 如果提供了 s3_endpoint_url，则优先使用它
            self.endpoint_url = settings.s3_endpoint_url

    def _client_config(self) -> Config:
        config = {"signature_version": self.signature_version}
        s3_config = {}
        if self.addressing_style in {"path", "virtual", "auto"}:
            s3_config["addressing_style"] = self.addressing_style
        if s3_config:
            config["s3"] = s3_config
        return Config(**config)

    def _client(self):
        return self.session.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_session_token=self.aws_session_token,
            region_name=self.region_name,
            config=self._client_config(),
        )

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        async with self._client() as s3:
            # 使用 upload_fileobj 流式上传，避免将整个文件加载到内存
            await s3.upload_fileobj(
                stream,
                self.bucket_name,
                save_path,
                ExtraArgs={"ContentType": content_type or "application/octet-stream"},
            )

    async def delete_file(self, file_code: StoredFile):
        async with self._client() as s3:
            await s3.delete_object(
                Bucket=self.bucket_name, Key=file_code.get_file_path()
            )

    async def get_file_response(self, file_code: StoredFile):
        try:
            filename = file_code.prefix + file_code.suffix
            content_length = None  # 初始化为 None，表示未知大小

            async with self._client() as s3:
                # 尝试获取文件大小（HEAD请求）；对象不存在时前置 404——
                # 与 local 后端语义一致（M2 行为统一），不能签出 200 的坏流
                try:
                    head_response = await s3.head_object(
                        Bucket=self.bucket_name,
                        Key=file_code.get_file_path()
                    )
                    # 从HEAD响应中获取Content-Length
                    if 'ContentLength' in head_response:
                        content_length = head_response['ContentLength']
                    elif 'Content-Length' in head_response['ResponseMetadata']['HTTPHeaders']:
                        content_length = int(head_response['ResponseMetadata']['HTTPHeaders']['Content-Length'])
                except ClientError as e:
                    error_code = e.response.get("Error", {}).get("Code", "")
                    if error_code in {"404", "NoSuchKey", "NotFound"}:
                        raise StorageError(
                            status_code=404, detail="文件已过期删除"
                        ) from e
                    # 其他 HEAD 错误不阻断：流式下载阶段会给出真实状态
                except Exception:
                    # 如果HEAD请求失败，则不提供 Content-Length
                    pass
                
                link = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": file_code.get_file_path(),
                    },
                    ExpiresIn=3600,
                )
            
            # 创建ClientSession并传递给生成器复用
            session = aiohttp.ClientSession()
            
            async def stream_generator():
                try:
                    async with session.get(link) as resp:
                        if resp.status != 200:
                            raise StorageError(
                                status_code=resp.status,
                                detail=f"从S3获取文件失败: {resp.status}"
                            )
                        # 设置块大小（例如64KB）
                        chunk_size = 65536
                        while True:
                            chunk = await resp.content.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    await session.close()
            
            headers = build_attachment_headers(filename, content_length)
            return StoredDownload(
                filename=filename,
                headers=headers,
                stream_factory=stream_generator,
                # 兜底关闭会话：客户端中断时与 generator finally 双保险
                background=BackgroundTask(session.close),
            )
        except StorageError:
            raise
        except Exception:
            raise StorageError(status_code=503, detail="服务代理下载异常，请稍后再试")

    async def get_file_url(self, file_code: StoredFile):
        if file_code.prefix == "文本分享":
            return file_code.text
        if self.proxy:
            return await get_file_url(file_code.code)
        else:
            async with self._client() as s3:
                result = await s3.generate_presigned_url(
                    "get_object",
                    Params={
                        "Bucket": self.bucket_name,
                        "Key": file_code.get_file_path(),
                    },
                    ExpiresIn=3600,
                )
                return result

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """
        保存分片到 S3（使用独立对象存储每个分片）
        注意：这里不使用 S3 原生的 multipart upload，而是将每个分片作为独立对象存储
        """
        chunk_key = str(Path(save_path).parent / "chunks" / upload_id / f"{chunk_index}.part")
        async with self._client() as s3:
            # 将分片作为独立对象上传
            await s3.put_object(
                Bucket=self.bucket_name,
                Key=chunk_key,
                Body=chunk_data,
                Metadata={
                    'chunk-hash': chunk_hash,
                    'chunk-index': str(chunk_index)
                }
            )

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """
        合并 S3 上的分片文件
        使用 S3 的 multipart upload API 实现流式合并，避免内存问题
        """
        file_sha256 = hashlib.sha256()
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)

        async with self._client() as s3:
            # 创建 multipart upload
            mpu = await s3.create_multipart_upload(
                Bucket=self.bucket_name,
                Key=save_path,
                ContentType='application/octet-stream'
            )
            mpu_id = mpu['UploadId']
            parts = []

            try:
                # 按顺序读取、验证每个分片；S3 multipart 规范要求除最后一片外
                # 每个部分 ≥5MB（EntityTooSmall），而分片大小由客户端决定（常见
                # 2-4MB）——因此缓冲到 S3_MIN_MULTIPART_PART_SIZE 再上传 part，
                # 内存上界 = 5MB + 单个分片，不破坏流式合并的初衷。
                part_buffer = bytearray()
                part_number = 0

                async def _flush_part():
                    nonlocal part_number
                    if not part_buffer:
                        return
                    part_number += 1
                    part_response = await s3.upload_part(
                        Bucket=self.bucket_name,
                        Key=save_path,
                        UploadId=mpu_id,
                        PartNumber=part_number,
                        Body=bytes(part_buffer),
                    )
                    parts.append({
                        'PartNumber': part_number,
                        'ETag': part_response['ETag']
                    })
                    part_buffer.clear()

                for i in range(total_chunks):
                    chunk_key = f"{chunk_dir}/{i}.part"
                    chunk_record = self._get_chunk_record(chunk_records, i)

                    try:
                        response = await s3.get_object(
                            Bucket=self.bucket_name,
                            Key=chunk_key
                        )
                        chunk_data = await response['Body'].read()
                    except Exception as e:
                        raise ValueError(f"分片{i}文件不存在: {e}")

                    self._verify_and_hash_chunk(i, chunk_record, chunk_data, file_sha256)
                    part_buffer.extend(chunk_data)
                    if len(part_buffer) >= S3_MIN_MULTIPART_PART_SIZE:
                        await _flush_part()

                # 收尾：剩余缓冲作为最后一个 part（S3 允许最后一片小于 5MB；
                # 恰好整除时缓冲为空，跳过）
                await _flush_part()

                # 完成 multipart upload
                await s3.complete_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=save_path,
                    UploadId=mpu_id,
                    MultipartUpload={'Parts': parts}
                )
            except Exception as e:
                # 出错时取消 multipart upload
                await s3.abort_multipart_upload(
                    Bucket=self.bucket_name,
                    Key=save_path,
                    UploadId=mpu_id
                )
                raise e

        return save_path, file_sha256.hexdigest()

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理 S3 上的临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        chunk_dir = str(Path(save_path).parent / "chunks" / upload_id)
        async with self._client() as s3:
            try:
                # 列出并删除所有分片对象
                paginator = s3.get_paginator('list_objects_v2')
                async for page in paginator.paginate(Bucket=self.bucket_name, Prefix=chunk_dir):
                    objects = page.get('Contents', [])
                    if objects:
                        delete_objects = [{'Key': obj['Key']} for obj in objects]
                        await s3.delete_objects(
                            Bucket=self.bucket_name,
                            Delete={'Objects': delete_objects}
                        )
            except Exception as e:
                logger.warning(f"清理 S3 分片数据时出错: {e}")

    async def generate_presigned_upload_url(self, save_path: str, expires_in: int = 900) -> Optional[str]:
        """
        生成S3预签名上传URL
        :param save_path: 文件保存路径
        :param expires_in: URL过期时间（秒），默认15分钟
        :return: 预签名PUT URL
        """
        async with self._client() as s3:
            return await s3.generate_presigned_url(
                "put_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": save_path,
                },
                ExpiresIn=expires_in,
            )

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在于S3
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        async with self._client() as s3:
            last_error = None
            for attempt in range(3):
                try:
                    await s3.head_object(Bucket=self.bucket_name, Key=save_path)
                    return True
                except Exception as e:
                    last_error = e
                    if attempt < 2:
                        await asyncio.sleep(0.2 * (attempt + 1))

            try:
                result = await s3.list_objects_v2(
                    Bucket=self.bucket_name,
                    Prefix=save_path,
                    MaxKeys=1,
                )
                for item in result.get("Contents", []):
                    if item.get("Key") == save_path:
                        return True
            except Exception as e:
                last_error = e

            logger.warning(f"S3文件确认失败 key={save_path}: {last_error}")
            return False


