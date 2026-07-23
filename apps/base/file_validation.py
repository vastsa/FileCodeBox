"""文件类型校验：扩展名 / MIME 白名单 + magic bytes 防伪造。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, UploadFile
from fnmatch import fnmatchcase

from core.settings import settings


@dataclass(frozen=True)
class FileKind:
    name: str
    extensions: tuple[str, ...]
    mimes: tuple[str, ...]
    signatures: tuple[bytes, ...]


FILE_KINDS: tuple[FileKind, ...] = (
    FileKind("png", (".png",), ("image/png",), (b"\x89PNG\r\n\x1a\n",)),
    FileKind("jpg", (".jpg", ".jpeg"), ("image/jpeg",), (b"\xff\xd8\xff",)),
    FileKind("gif", (".gif",), ("image/gif",), (b"GIF87a", b"GIF89a")),
    FileKind("webp", (".webp",), ("image/webp",), ()),
    FileKind("bmp", (".bmp",), ("image/bmp", "image/x-ms-bmp"), (b"BM",)),
    FileKind("pdf", (".pdf",), ("application/pdf",), (b"%PDF",)),
    FileKind(
        "zip",
        (".zip", ".docx", ".xlsx", ".pptx", ".apk", ".jar"),
        (
            "application/zip",
            "application/x-zip-compressed",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "application/vnd.openxmlformats-officedocument.presentationml.presentation",
            "application/java-archive",
            "application/vnd.android.package-archive",
        ),
        (b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08"),
    ),
    FileKind(
        "rar",
        (".rar",),
        ("application/x-rar-compressed", "application/vnd.rar"),
        (b"Rar!\x1a\x07\x00", b"Rar!\x1a\x07\x01\x00"),
    ),
    FileKind("7z", (".7z",), ("application/x-7z-compressed",), (b"7z\xbc\xaf'\x1c",)),
    FileKind("gz", (".gz", ".tgz"), ("application/gzip", "application/x-gzip"), (b"\x1f\x8b",)),
    FileKind(
        "mp3",
        (".mp3",),
        ("audio/mpeg",),
        (b"ID3", b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"),
    ),
    FileKind("mp4", (".mp4", ".m4a", ".mov"), ("video/mp4", "audio/mp4", "video/quicktime"), ()),
    FileKind(
        "exe",
        (".exe", ".dll", ".sys"),
        ("application/x-msdownload", "application/x-dosexec"),
        (b"MZ",),
    ),
    FileKind("elf", (".elf", ".so", ".o"), ("application/x-executable",), (b"\x7fELF",)),
)

KNOWN_EXTENSIONS = {ext for kind in FILE_KINDS for ext in kind.extensions}


def normalize_allowed_file_types() -> list[str]:
    raw_value = settings.allowed_file_types
    if isinstance(raw_value, str):
        values = [item.strip() for item in raw_value.split(",")]
    elif isinstance(raw_value, (list, tuple, set)):
        values = [str(item).strip() for item in raw_value]
    else:
        values = []
    normalized = [item.lower() for item in values if item]
    return normalized or ["*"]


def _extension_of(file_name: str) -> str:
    return Path(file_name or "").suffix.lower()


def _match_allow_rule(rule: str, file_name: str, content_type: str) -> bool:
    if rule in {"*", "*/*"}:
        return True
    if "/" in rule:
        return fnmatchcase(content_type, rule)
    extension = rule if rule.startswith(".") else f".{rule}"
    return file_name.endswith(extension)


def is_type_allowed(file_name: str, content_type: Optional[str] = None) -> bool:
    allowed = normalize_allowed_file_types()
    if any(rule in {"*", "*/*"} for rule in allowed):
        return True
    normalized_name = (file_name or "").strip().lower()
    normalized_content_type = (content_type or "").strip().lower()
    return any(
        _match_allow_rule(rule, normalized_name, normalized_content_type)
        for rule in allowed
    )


def detect_file_kind(header: bytes) -> Optional[FileKind]:
    if not header:
        return None

    if len(header) >= 12 and header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return next(kind for kind in FILE_KINDS if kind.name == "webp")

    if len(header) >= 12 and header[4:8] == b"ftyp":
        return next(kind for kind in FILE_KINDS if kind.name == "mp4")

    candidates: list[tuple[int, FileKind]] = []
    for kind in FILE_KINDS:
        for signature in kind.signatures:
            if signature and header.startswith(signature):
                candidates.append((len(signature), kind))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def validate_file_type(file_name: str, content_type: Optional[str] = None) -> None:
    if not is_type_allowed(file_name, content_type):
        raise HTTPException(status_code=403, detail="不允许上传该类型文件")


def _kind_matches_ext(kind: FileKind, extension: str) -> bool:
    return extension in kind.extensions


def _kind_matches_mime(kind: FileKind, mime: str) -> bool:
    return mime in kind.mimes


def validate_file_magic(
    file_name: str,
    content_type: Optional[str],
    header: Optional[bytes],
) -> None:
    """白名单通过后，用 magic bytes 防止扩展名 / MIME 伪造。"""
    validate_file_type(file_name, content_type)
    if not header:
        return

    claimed_ext = _extension_of(file_name)
    claimed_mime = (content_type or "").strip().lower()
    detected = detect_file_kind(header)

    if claimed_ext in KNOWN_EXTENSIONS:
        if detected is None or not _kind_matches_ext(detected, claimed_ext):
            raise HTTPException(
                status_code=403,
                detail="文件内容与扩展名不匹配，疑似伪造类型",
            )

    if claimed_mime and any(claimed_mime in kind.mimes for kind in FILE_KINDS):
        if detected is None or not _kind_matches_mime(detected, claimed_mime):
            raise HTTPException(
                status_code=403,
                detail="文件内容与 Content-Type 不匹配，疑似伪造类型",
            )

    allowed = normalize_allowed_file_types()
    if detected and not any(rule in {"*", "*/*"} for rule in allowed):
        allowed_by_detected = any(
            is_type_allowed(f"file{ext}", mime)
            for ext in detected.extensions
            for mime in (detected.mimes or (None,))
        )
        if not allowed_by_detected:
            raise HTTPException(status_code=403, detail="不允许上传该类型文件")


async def read_upload_header(file: UploadFile, size: int = 64) -> bytes:
    await file.seek(0)
    header = await file.read(size)
    await file.seek(0)
    return header or b""


async def validate_upload_file(file: UploadFile) -> None:
    header = await read_upload_header(file)
    validate_file_magic(file.filename or "", file.content_type, header)


def validate_header_bytes(
    file_name: str, content_type: Optional[str], header: bytes
) -> None:
    validate_file_magic(file_name, content_type, header)
