"""Storage backend package (split from the former 1400+ line storage.py).

Public surface is re-exported here — `from core.storage import X` keeps
working for every historical name.

Backends load lazily: importing this package only pulls in ``_base`` (the
framework-free contracts). Selecting ``local`` therefore never imports
aioboto3/botocore/aiohttp, which is the bulk of the resident memory on a
small VPS. ``storages[name]()`` keeps its historical shape; backends that
opt in via ``cache_signature()`` are also reused across requests while their
configuration is unchanged (previously every request rebuilt e.g. an
``aioboto3.Session``).
"""
from __future__ import annotations

from importlib import import_module
from typing import Callable

from core.storage._base import (  # noqa: F401
    FileStorageInterface,
    S3_MIN_MULTIPART_PART_SIZE,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)

# 历史导出名 -> (模块, 类名)。模块级 __getattr__ 与惰性工厂共用这张表。
_LAZY_EXPORTS: dict[str, tuple[str, str]] = {
    "SystemFileStorage": ("core.storage.local", "SystemFileStorage"),
    "S3FileStorage": ("core.storage.s3", "S3FileStorage"),
    "OneDriveFileStorage": ("core.storage.onedrive", "OneDriveFileStorage"),
    "OpenDALFileStorage": ("core.storage.opendal", "OpenDALFileStorage"),
    "WebDAVFileStorage": ("core.storage.webdav", "WebDAVFileStorage"),
}


def _load_class(module_name: str, attr: str):
    return getattr(import_module(module_name), attr)


class _StorageFactory:
    """Lazily import a backend class and reuse its instance while config holds.

    Call sites continue to use ``storages[name]()``. Backends exposing a
    ``cache_signature()`` classmethod are constructed once per configuration
    and reused; a changed signature rebuilds the instance. ``local`` and
    ``onedrive`` deliberately omit it (see their module notes).
    """

    def __init__(self, module_name: str, attr: str):
        self._module_name = module_name
        self._attr = attr
        self._cached: tuple[object, FileStorageInterface] | None = None

    @property
    def storage_class(self):
        return _load_class(self._module_name, self._attr)

    def __call__(self) -> FileStorageInterface:
        cls = self.storage_class
        signature_fn = getattr(cls, "cache_signature", None)
        if signature_fn is None:
            return cls()
        signature = signature_fn()
        if self._cached is not None and self._cached[0] == signature:
            return self._cached[1]
        instance = cls()
        self._cached = (signature, instance)
        return instance

    def __repr__(self) -> str:
        return f"<storage factory {self._attr}>"


storages: dict[str, Callable[[], FileStorageInterface]] = {
    "local": _StorageFactory("core.storage.local", "SystemFileStorage"),
    "s3": _StorageFactory("core.storage.s3", "S3FileStorage"),
    "onedrive": _StorageFactory("core.storage.onedrive", "OneDriveFileStorage"),
    "opendal": _StorageFactory("core.storage.opendal", "OpenDALFileStorage"),
    "webdav": _StorageFactory("core.storage.webdav", "WebDAVFileStorage"),
}


def __getattr__(name: str):
    target = _LAZY_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    value = _load_class(*target)
    globals()[name] = value  # 缓存解析结果，后续访问不再经过 __getattr__
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(_LAZY_EXPORTS))
