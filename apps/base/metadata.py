"""文件与寄件管理共用的用户元数据归一化规则。"""

from typing import Any


def normalize_metadata_note(value: Any) -> str:
    """备注转为文本、去除首尾空白，并限制为 2000 个字符。"""
    return "" if value is None else str(value).strip()[:2000]


def normalize_metadata_tags(value: Any) -> list[str]:
    """标签最多 12 个、单项 24 字符，并按忽略大小写规则去重。"""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list):
        return []
    result, seen = [], set()
    for raw_tag in value:
        tag = str(raw_tag).strip()[:24]
        if not tag or tag.lower() in seen:
            continue
        seen.add(tag.lower())
        result.append(tag)
        if len(result) == 12:
            break
    return result
