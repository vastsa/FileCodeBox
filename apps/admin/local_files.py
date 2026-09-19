"""Admin-side local (NAS) file browsing and deletion."""
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from apps.base.local_share import (
    MAX_LIST_ENTRIES,
    format_local_ctime,
    get_local_root,
    normalize_local_relpath,
    resolve_under_local,
)


class LocalFileService:
    async def list_files(self, path: str = ""):
        relpath = normalize_local_relpath(path, allow_empty=True)
        directory = resolve_under_local(relpath)
        if not directory.exists() or not directory.is_dir():
            raise HTTPException(status_code=404, detail="目录不存在")

        root = get_local_root()
        items: list[dict[str, Any]] = []
        try:
            children = list(directory.iterdir())
        except OSError as exc:
            raise HTTPException(status_code=500, detail="无法读取目录") from exc

        children.sort(key=lambda p: (not p.is_dir(), p.name.lower()))
        truncated = False
        for child in children:
            if len(items) >= MAX_LIST_ENTRIES:
                truncated = True
                break
            try:
                resolved = child.resolve()
                resolved.relative_to(root)
            except (OSError, ValueError):
                continue
            if not resolved.is_file() and not resolved.is_dir():
                continue
            child_rel = child.name if not relpath else f"{relpath}/{child.name}"
            is_dir = resolved.is_dir()
            items.append(
                {
                    "file": child.name,
                    "name": child.name,
                    "path": child_rel,
                    "type": "dir" if is_dir else "file",
                    "ctime": format_local_ctime(resolved),
                    "size": None if is_dir else resolved.stat().st_size,
                }
            )

        parent = ""
        if relpath:
            parent_path = Path(relpath).parent.as_posix()
            parent = "" if parent_path == "." else parent_path
        return {
            "path": relpath,
            "parent": parent,
            "truncated": truncated,
            "items": items,
        }

    async def delete_file(self, filename: str):
        file = LocalFileClass(filename)
        if await file.exists():
            await file.delete()
            return "删除成功"
        raise HTTPException(status_code=404, detail="文件不存在")


class LocalFileClass:
    def __init__(self, file):
        relpath = normalize_local_relpath(file)
        self.file = relpath
        self.name = Path(relpath).name
        self.path = resolve_under_local(relpath)
        if self.path.is_file():
            self.ctime = format_local_ctime(self.path)
            self.size = self.path.stat().st_size
        else:
            self.ctime = None
            self.size = None

    async def read(self) -> bytes:
        with open(self.path, "rb") as fh:
            return fh.read()

    async def delete(self):
        if not self.path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        self.path.unlink()

    async def exists(self):
        return self.path.is_file()
