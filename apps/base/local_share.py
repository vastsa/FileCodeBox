"""Local NAS-style share helpers.

Files under ``data/local`` can be browsed by admin and turned into extract
codes without copying them into ``data/share``. The original file is never
deleted when a share expires or is removed from the file list.

``FileCodes.file_path`` is the sentinel ``local-ref``; ``uuid_file_name``
stores the posix relative path under ``data/local``. Accidental storage
deletes therefore look at ``data/local-ref/...`` and cannot touch the
original NAS file.
"""
from __future__ import annotations

import time
from pathlib import Path
from urllib.parse import quote

from fastapi import HTTPException

from core.errors import StorageError
from core.storage import StoredDownload

LOCAL_REF_MARKER = "local-ref"
MAX_RELPATH_LEN = 255
MAX_LIST_ENTRIES = 500


def is_local_ref(file_code) -> bool:
    return (getattr(file_code, "file_path", None) or "") == LOCAL_REF_MARKER


def should_skip_storage_delete(file_code) -> bool:
    return is_local_ref(file_code) or getattr(file_code, "text", None) is not None


def get_local_root() -> Path:
    from core.settings import data_root

    root = (Path(data_root) / "local").resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def normalize_local_relpath(raw: str, *, allow_empty: bool = False) -> str:
    text = str(raw or "").replace("\\", "/").strip()
    if not text:
        if allow_empty:
            return ""
        raise HTTPException(status_code=400, detail="非法文件名")
    if (
        text in {".", ".."}
        or text.startswith("/")
        or text.startswith("~")
        or "\x00" in text
        or ":" in text.split("/", 1)[0]
    ):
        raise HTTPException(status_code=400, detail="非法文件名")

    parts = [part for part in text.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        raise HTTPException(status_code=400, detail="非法文件名")

    relpath = "/".join(parts)
    if len(relpath) > MAX_RELPATH_LEN:
        raise HTTPException(status_code=400, detail="路径过长")
    return relpath


def resolve_under_local(relpath: str) -> Path:
    root = get_local_root()
    if not relpath:
        return root
    candidate = (root / relpath).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="非法文件路径") from exc
    return candidate


def format_local_ctime(path: Path) -> str | None:
    try:
        return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(path.stat().st_ctime))
    except OSError:
        return None


def build_local_ref_download(file_code) -> StoredDownload:
    try:
        relpath = normalize_local_relpath(getattr(file_code, "uuid_file_name", None) or "")
        path = resolve_under_local(relpath)
    except HTTPException as exc:
        raise StorageError(status_code=404, detail="文件已过期删除") from exc
    if not path.is_file():
        raise StorageError(status_code=404, detail="文件已过期删除")

    filename = f"{getattr(file_code, 'prefix', '') or ''}{getattr(file_code, 'suffix', '') or ''}"
    if not filename:
        filename = path.name
    encoded_filename = quote(filename, safe="")
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}"}
    try:
        headers["Content-Length"] = str(path.stat().st_size)
    except OSError:
        pass
    return StoredDownload(filename=filename, headers=headers, path=path)
