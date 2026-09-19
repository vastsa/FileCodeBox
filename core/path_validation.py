"""设置和寄件配置共用目录校验，仅验证输入，不改变各自的路径生成规则。"""

import re
from pathlib import PurePosixPath


def validate_storage_directory(value: str, *, allow_empty: bool = False, max_length: int = 200) -> str:
    """限制为存储根目录内的相对目录，跨本地、对象存储和 WebDAV 使用同一规则。"""
    if not isinstance(value, str):
        raise ValueError("存储目录必须是字符串")
    value = value.strip()
    if not value and allow_empty:
        return ""
    parts = value.split("/")
    if (
        not value or len(value) > max_length
        or PurePosixPath(value).is_absolute()
        or not re.fullmatch(r"[\w ./-]+", value, re.UNICODE)
        or any(part in {"", ".", ".."} for part in parts)
        or any(part.endswith((".", " ")) for part in parts)
        or any(re.fullmatch(r"(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(\..*)?", part) for part in parts)
    ):
        raise ValueError(f"存储目录须为 {max_length} 字以内的相对路径，如 inbox/project-a；不能包含绝对路径、路径跳转或保留名称")
    return value
