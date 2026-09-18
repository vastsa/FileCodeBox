"""Storage backend package (split from the former 1400+ line storage.py).

Public surface is re-exported here — `from core.storage import X` keeps
working for every historical name.
"""
from core.storage._base import (  # noqa: F401
    FileStorageInterface,
    S3_MIN_MULTIPART_PART_SIZE,
    StoredDownload,
    StoredFile,
    build_attachment_headers,
)
from core.storage.local import SystemFileStorage  # noqa: F401
from core.storage.s3 import S3FileStorage  # noqa: F401
from core.storage.onedrive import OneDriveFileStorage  # noqa: F401
from core.storage.opendal import OpenDALFileStorage  # noqa: F401
from core.storage.webdav import WebDAVFileStorage  # noqa: F401

storages = {
    "local": SystemFileStorage,
    "s3": S3FileStorage,
    "onedrive": OneDriveFileStorage,
    "opendal": OpenDALFileStorage,
    "webdav": WebDAVFileStorage,
}
