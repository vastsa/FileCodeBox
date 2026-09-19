# @Time    : 2023/8/11 20:06
# @Author  : Lan
# @File    : storage.py
# @Software: PyCharm
import hashlib
from typing import BinaryIO, Optional
from urllib.parse import quote

from collections.abc import Callable
from typing import Any
from dataclasses import dataclass
from pathlib import Path


@dataclass


class StoredDownload:
    """Framework-free description of a file download.

    Backends return this; the view layer builds the starlette Response:
    - ``path`` set -> FileResponse (local files, Range support for free)
    - ``content`` set -> small full-read Response (legacy OpenDAL fallback)
    - ``stream_factory`` set -> StreamingResponse(stream_factory(), ...)
    ``background`` is an optional response-sent cleanup hook.
    """

    filename: str
    headers: dict
    media_type: str = "application/octet-stream"
    path: Path | None = None
    content: bytes | None = None
    stream_factory: Callable[[], Any] | None = None
    background: Any = None  # starlette BackgroundTask（core 层不 import starlette）


@dataclass
class StoredFile:
    """Plain, framework- and ORM-free description of a stored file.

    Storage backends accept this instead of ORM models so core/ never imports
    apps/. Callers (views/tasks/services) build it from their own records.
    """

    file_path: str
    uuid_file_name: str
    code: str = ""
    prefix: str = ""
    suffix: str = ""
    text: str = ""

    def get_file_path(self) -> str:
        return f"{self.file_path}/{self.uuid_file_name}"




# S3 multipart 除最后一片外每部分最小 5MB（服务端强制，小于即 EntityTooSmall）
S3_MIN_MULTIPART_PART_SIZE = 5 * 1024 * 1024


def build_attachment_headers(filename: str, content_length=None) -> dict:
    """所有存储后端统一的下载响应头。

    Content-Disposition: attachment 是防御存储型 XSS 的关键——同源下载路径
    （/share/download）因此永不内联渲染 HTML/SVG。此函数是唯一构造点，
    新增后端必须复用（tests/test_attachment_guard.py 有源码级 tripwire）。
    """
    encoded_filename = quote(filename, safe="")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    if content_length is not None:
        headers["Content-Length"] = str(content_length)
    return headers

class FileStorageInterface:

    @staticmethod
    def _get_chunk_record(chunk_records: dict, index: int):
        """Look up the caller-provided record for chunk `index`.

        Records are plain objects exposing ``chunk_hash``; fetching them from
        the DB is the caller's job (keeps storage ORM-free).
        """
        chunk_record = chunk_records.get(index)
        if not chunk_record:
            raise ValueError(f"分片{index}记录不存在")
        return chunk_record

    def _verify_and_hash_chunk(
        self,
        index: int,
        chunk_record,
        chunk_data: bytes,
        file_sha256,
    ) -> None:
        """Verify a chunk against its recorded hash, then stripe it into the
        whole-file digest. Raises the shared ValueError wording on mismatch."""
        current_hash = hashlib.sha256(chunk_data).hexdigest()
        if current_hash != chunk_record.chunk_hash:
            raise ValueError(
                f"分片{index}哈希不匹配: 期望 {chunk_record.chunk_hash}, 实际 {current_hash}"
            )
        file_sha256.update(chunk_data)

    async def save_file(
        self, stream: BinaryIO, save_path: str, content_type: Optional[str] = None
    ):
        """Save a binary stream (caller owns closing the stream)."""
        raise NotImplementedError

    async def delete_file(self, file_code: StoredFile):
        """
        删除文件
        """
        raise NotImplementedError

    async def get_file_url(self, file_code: StoredFile):
        """
        获取文件分享的url

        如果服务不支持直接访问文件，可以通过服务器中转下载。
        此时，此方法可以调用 utils.py 中的 `get_file_url` 方法，获取服务器中转下载的url
        """
        raise NotImplementedError

    async def get_file_response(self, file_code: StoredFile):
        """
        获取文件响应

        如果服务不支持直接访问文件，则需要实现该方法，返回文件响应
        其余情况，可以不实现该方法
        """
        raise NotImplementedError

    async def save_chunk(self, upload_id: str, chunk_index: int, chunk_data: bytes, chunk_hash: str, save_path: str):
        """
        保存分片文件
        :param upload_id: 上传会话ID
        :param chunk_index: 分片索引
        :param chunk_data: 分片数据
        :param chunk_hash: 分片哈希值
        :param save_path: 文件保存路径
        """
        raise NotImplementedError

    async def merge_chunks(self, upload_id: str, total_chunks: int, chunk_size: int, save_path: str, chunk_records: dict) -> tuple[str, str]:
        """
        合并分片文件并返回文件路径和完整哈希值
        :param upload_id: 上传会话ID
        :param chunk_info: 分片信息
        :param save_path: 文件保存路径
        :return: (文件路径, 文件哈希值)
        """
        raise NotImplementedError

    async def generate_presigned_upload_url(self, save_path: str, expires_in: int = 900) -> Optional[str]:
        """
        生成预签名上传URL
        :param save_path: 文件保存路径
        :param expires_in: URL过期时间（秒），默认15分钟
        :return: 预签名URL，如果不支持直传则返回None
        """
        return None  # 默认不支持直传，使用代理模式

    async def file_exists(self, save_path: str) -> bool:
        """
        检查文件是否存在
        :param save_path: 文件路径
        :return: 文件是否存在
        """
        raise NotImplementedError

    async def clean_chunks(self, upload_id: str, save_path: str):
        """
        清理临时分片文件
        :param upload_id: 上传会话ID
        :param save_path: 文件保存路径
        """
        raise NotImplementedError


