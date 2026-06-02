import os
import time
from datetime import datetime
from typing import Any, Optional

from core.response import APIResponse
from core.storage import FileStorageInterface, storages
from core.settings import settings
from core.config import refresh_settings
from apps.base.models import FileCodes, KeyValue, file_codes_pydantic
from apps.base.utils import get_expire_info, get_file_path_name
from fastapi import HTTPException
from core.settings import data_root
from core.utils import get_now, hash_password, is_password_hashed


class FileService:
    SORT_FIELDS = {
        "created_at",
        "createdat",
        "expired_at",
        "expiredat",
        "name",
        "size",
        "used_count",
        "usedcount",
        "code",
    }

    def __init__(self):
        self.file_storage: FileStorageInterface = storages[settings.file_storage]()

    async def _delete_file_code(self, file_code: FileCodes):
        if file_code.text is None:
            await self.file_storage.delete_file(file_code)
        await file_code.delete()

    async def delete_file(self, file_id: int):
        file_code = await FileCodes.get(id=file_id)
        await self._delete_file_code(file_code)

    async def delete_files(self, file_ids: list[int]):
        unique_ids = list(dict.fromkeys(file_ids))
        deleted = []
        failed = []
        missing = []

        for file_id in unique_ids:
            file_code = await FileCodes.filter(id=file_id).first()
            if not file_code:
                missing.append(file_id)
                continue

            try:
                await self._delete_file_code(file_code)
                deleted.append(file_id)
            except Exception as exc:
                failed.append({"id": file_id, "reason": str(exc)})

        return {
            "requestedCount": len(file_ids),
            "requested_count": len(file_ids),
            "uniqueCount": len(unique_ids),
            "unique_count": len(unique_ids),
            "deletedCount": len(deleted),
            "deleted_count": len(deleted),
            "missingCount": len(missing),
            "missing_count": len(missing),
            "failedCount": len(failed),
            "failed_count": len(failed),
            "deleted": deleted,
            "missing": missing,
            "failed": failed,
        }

    async def update_files(self, file_ids: list[int], update_data: dict[str, Any]):
        unique_ids = list(dict.fromkeys(file_ids))
        updated = []
        failed = []
        missing = []

        for file_id in unique_ids:
            file_code = await FileCodes.filter(id=file_id).first()
            if not file_code:
                missing.append(file_id)
                continue

            try:
                await file_code.update_from_dict(update_data).save()
                updated.append(file_id)
            except Exception as exc:
                failed.append({"id": file_id, "reason": str(exc)})

        return {
            "requestedCount": len(file_ids),
            "requested_count": len(file_ids),
            "uniqueCount": len(unique_ids),
            "unique_count": len(unique_ids),
            "updatedCount": len(updated),
            "updated_count": len(updated),
            "missingCount": len(missing),
            "missing_count": len(missing),
            "failedCount": len(failed),
            "failed_count": len(failed),
            "updated": updated,
            "missing": missing,
            "failed": failed,
        }

    async def list_files(
        self,
        page: int,
        size: int,
        keyword: str = "",
        status: str = "",
        file_type: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        page = max(page, 1)
        size = min(max(size, 1), 100)
        keyword = keyword.strip().lower()
        status = status.strip().lower()
        file_type = file_type.strip().lower()
        sort_by = self._normalize_sort_by(sort_by)
        reverse = sort_order.strip().lower() != "asc"

        all_files = await FileCodes.all()
        enriched_files = []
        summary = {
            "totalFiles": len(all_files),
            "activeCount": 0,
            "expiredCount": 0,
            "textCount": 0,
            "fileCount": 0,
            "chunkedCount": 0,
            "storageUsed": sum(file_code.size for file_code in all_files),
            "usedCount": sum(file_code.used_count for file_code in all_files),
        }

        for file_code in all_files:
            item = await self._build_admin_file_item(file_code)
            if item["isExpired"]:
                summary["expiredCount"] += 1
            else:
                summary["activeCount"] += 1
            if item["isText"]:
                summary["textCount"] += 1
            else:
                summary["fileCount"] += 1
            if item["isChunked"]:
                summary["chunkedCount"] += 1

            if not self._match_admin_file(item, keyword, status, file_type):
                continue
            enriched_files.append(item)

        enriched_files.sort(
            key=lambda item: self._get_sort_value(item, sort_by),
            reverse=reverse,
        )
        offset = (page - 1) * size
        return enriched_files[offset : offset + size], len(enriched_files), summary

    async def _build_admin_file_item(self, file_code: FileCodes) -> dict[str, Any]:
        is_text = file_code.text is not None
        is_expired = await file_code.is_expired()
        name = f"{file_code.prefix}{file_code.suffix}"
        remaining_downloads = (
            max(file_code.expired_count, 0) if file_code.expired_count >= 0 else None
        )
        item = await file_codes_pydantic.from_tortoise_orm(file_code)
        data = item.model_dump()
        data.update(
            {
                "name": name,
                "type": "text" if is_text else "file",
                "status": "expired" if is_expired else "active",
                "isText": is_text,
                "is_text": is_text,
                "isExpired": is_expired,
                "is_expired": is_expired,
                "isChunked": file_code.is_chunked,
                "is_chunked": file_code.is_chunked,
                "remainingDownloads": remaining_downloads,
                "remaining_downloads": remaining_downloads,
                "usedCount": file_code.used_count,
                "used_count": file_code.used_count,
                "createdAt": file_code.created_at,
                "created_at": file_code.created_at,
                "expiredAt": file_code.expired_at,
                "expired_at": file_code.expired_at,
                "fileHash": file_code.file_hash,
                "file_hash": file_code.file_hash,
            }
        )
        return data

    async def get_file_detail(self, file_id: int):
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")

        detail = await self._build_admin_file_item(file_code)
        is_text = file_code.text is not None
        has_download_limit = file_code.expired_count >= 0
        is_permanent = file_code.expired_at is None and file_code.expired_count < 0
        text_length = len(file_code.text) if file_code.text else 0
        can_download = is_text or bool(file_code.file_path or file_code.uuid_file_name)
        now = await get_now()
        status_insights = self._build_file_status_insights(
            file_code=file_code,
            detail=detail,
            now=now,
            has_download_limit=has_download_limit,
            is_permanent=is_permanent,
            can_download=can_download,
        )
        timeline = self._build_file_timeline(
            file_code=file_code,
            detail=detail,
            now=now,
            has_download_limit=has_download_limit,
            is_permanent=is_permanent,
            is_text=is_text,
        )

        detail.update(
            {
                "filename": detail["name"],
                "displayName": detail["name"],
                "display_name": detail["name"],
                "isPermanent": is_permanent,
                "is_permanent": is_permanent,
                "hasDownloadLimit": has_download_limit,
                "has_download_limit": has_download_limit,
                "hasExpirationTime": file_code.expired_at is not None,
                "has_expiration_time": file_code.expired_at is not None,
                "textLength": text_length,
                "text_length": text_length,
                "canPreviewText": is_text,
                "can_preview_text": is_text,
                "canDownload": can_download,
                "can_download": can_download,
                "storageBackend": settings.file_storage,
                "storage_backend": settings.file_storage,
                "filePath": file_code.file_path,
                "file_path": file_code.file_path,
                "uuidFileName": file_code.uuid_file_name,
                "uuid_file_name": file_code.uuid_file_name,
                "uploadId": file_code.upload_id,
                "upload_id": file_code.upload_id,
                "policy": {
                    "expiredAt": file_code.expired_at,
                    "expired_at": file_code.expired_at,
                    "expiredCount": file_code.expired_count,
                    "expired_count": file_code.expired_count,
                    "remainingDownloads": detail["remainingDownloads"],
                    "remaining_downloads": detail["remaining_downloads"],
                    "isExpired": detail["isExpired"],
                    "is_expired": detail["is_expired"],
                    "isPermanent": is_permanent,
                    "is_permanent": is_permanent,
                },
                "storage": {
                    "backend": settings.file_storage,
                    "filePath": file_code.file_path,
                    "file_path": file_code.file_path,
                    "uuidFileName": file_code.uuid_file_name,
                    "uuid_file_name": file_code.uuid_file_name,
                    "fileHash": file_code.file_hash,
                    "file_hash": file_code.file_hash,
                    "isChunked": file_code.is_chunked,
                    "is_chunked": file_code.is_chunked,
                    "uploadId": file_code.upload_id,
                    "upload_id": file_code.upload_id,
                },
                "statusInsights": status_insights,
                "status_insights": status_insights,
                "timeline": timeline,
            }
        )
        return detail

    def _build_file_status_insights(
        self,
        file_code: FileCodes,
        detail: dict[str, Any],
        now: datetime,
        has_download_limit: bool,
        is_permanent: bool,
        can_download: bool,
    ) -> dict[str, Any]:
        remaining_downloads = detail["remainingDownloads"]
        seconds_until_expiration = self._seconds_between(now, file_code.expired_at)
        age_seconds = self._seconds_between(file_code.created_at, now)
        reasons = []

        if detail["isExpired"]:
            reasons.append("expired")
        if has_download_limit and remaining_downloads == 0:
            reasons.append("download_limit_exhausted")
        if seconds_until_expiration is not None and 0 < seconds_until_expiration <= 86400:
            reasons.append("expires_soon")
        if file_code.used_count == 0:
            reasons.append("never_retrieved")
        if not can_download:
            reasons.append("storage_metadata_incomplete")
        if file_code.is_chunked:
            reasons.append("chunked_upload")

        severity = "success"
        state = "available"
        next_action = "monitor"
        if detail["isExpired"] or (has_download_limit and remaining_downloads == 0):
            severity = "danger"
            state = "expired"
            next_action = "extend_or_delete"
        elif not can_download:
            severity = "danger"
            state = "storage_incomplete"
            next_action = "inspect_storage"
        elif "expires_soon" in reasons:
            severity = "warning"
            state = "expiring_soon"
            next_action = "extend_expiration"
        elif is_permanent:
            state = "permanent"
            next_action = "monitor"

        return {
            "severity": severity,
            "state": state,
            "nextAction": next_action,
            "next_action": next_action,
            "reasons": reasons,
            "metrics": {
                "ageSeconds": max(age_seconds or 0, 0),
                "age_seconds": max(age_seconds or 0, 0),
                "secondsUntilExpiration": seconds_until_expiration,
                "seconds_until_expiration": seconds_until_expiration,
                "remainingDownloads": remaining_downloads,
                "remaining_downloads": remaining_downloads,
                "usedCount": file_code.used_count,
                "used_count": file_code.used_count,
            },
        }

    def _build_file_timeline(
        self,
        file_code: FileCodes,
        detail: dict[str, Any],
        now: datetime,
        has_download_limit: bool,
        is_permanent: bool,
        is_text: bool,
    ) -> list[dict[str, Any]]:
        remaining_downloads = detail["remainingDownloads"]
        seconds_until_expiration = self._seconds_between(now, file_code.expired_at)
        timeline = [
            {
                "key": "created",
                "status": "done",
                "severity": "success",
                "timestamp": file_code.created_at,
            },
            {
                "key": "content_ready",
                "status": "done",
                "severity": "success",
                "timestamp": file_code.created_at,
                "detail": "text" if is_text else "file",
            },
        ]

        if file_code.upload_id:
            timeline.append(
                {
                    "key": "upload_session",
                    "status": "done",
                    "severity": "info",
                    "timestamp": file_code.created_at,
                    "detail": file_code.upload_id,
                }
            )

        if is_permanent:
            timeline.append(
                {
                    "key": "expiration_policy",
                    "status": "unlimited",
                    "severity": "success",
                    "timestamp": None,
                }
            )
        elif file_code.expired_at is not None:
            expired = seconds_until_expiration is not None and seconds_until_expiration <= 0
            timeline.append(
                {
                    "key": "expiration_policy",
                    "status": "expired" if expired else "pending",
                    "severity": "danger" if expired else "warning",
                    "timestamp": file_code.expired_at,
                    "value": seconds_until_expiration,
                }
            )

        if has_download_limit:
            exhausted = remaining_downloads == 0
            timeline.append(
                {
                    "key": "download_limit",
                    "status": "exhausted" if exhausted else "active",
                    "severity": "danger" if exhausted else "info",
                    "timestamp": None,
                    "value": remaining_downloads,
                }
            )
        else:
            timeline.append(
                {
                    "key": "download_limit",
                    "status": "unlimited",
                    "severity": "success",
                    "timestamp": None,
                    "value": None,
                }
            )

        timeline.append(
            {
                "key": "retrieved",
                "status": "done" if file_code.used_count > 0 else "pending",
                "severity": "success" if file_code.used_count > 0 else "neutral",
                "timestamp": None,
                "value": file_code.used_count,
            }
        )
        return timeline

    def _seconds_between(
        self, start: Optional[datetime], end: Optional[datetime]
    ) -> Optional[int]:
        if start is None or end is None:
            return None
        if start.tzinfo is None and end.tzinfo is not None:
            end = end.replace(tzinfo=None)
        elif start.tzinfo is not None and end.tzinfo is None:
            start = start.replace(tzinfo=None)
        return int((end - start).total_seconds())

    def _match_admin_file(
        self,
        item: dict[str, Any],
        keyword: str,
        status: str,
        file_type: str,
    ) -> bool:
        if status == "active" and item["isExpired"]:
            return False
        if status == "expired" and not item["isExpired"]:
            return False
        if file_type == "text" and not item["isText"]:
            return False
        if file_type == "file" and item["isText"]:
            return False
        if file_type == "chunked" and not item["isChunked"]:
            return False
        if not keyword:
            return True

        search_values = [
            item.get("code"),
            item.get("name"),
            item.get("prefix"),
            item.get("suffix"),
            item.get("fileHash"),
            item.get("text"),
        ]
        return any(keyword in str(value).lower() for value in search_values if value)

    def _normalize_sort_by(self, sort_by: str) -> str:
        normalized = sort_by.replace("-", "_").strip().lower()
        if normalized not in self.SORT_FIELDS:
            return "created_at"
        return normalized

    def _get_sort_value(self, item: dict[str, Any], sort_by: str):
        def date_value(value: Any) -> float:
            if value is None:
                return 0
            if isinstance(value, datetime):
                return value.timestamp()
            return 0

        sort_map = {
            "created_at": date_value(item.get("createdAt")),
            "createdat": date_value(item.get("createdAt")),
            "expired_at": date_value(item.get("expiredAt")),
            "expiredat": date_value(item.get("expiredAt")),
            "name": item.get("name") or "",
            "size": item.get("size") or 0,
            "used_count": item.get("usedCount") or 0,
            "usedcount": item.get("usedCount") or 0,
            "code": item.get("code") or "",
        }
        return sort_map.get(sort_by)

    async def download_file(self, file_id: int):
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")
        if file_code.text:
            return APIResponse(detail=file_code.text)
        else:
            return await self.file_storage.get_file_response(file_code)

    async def preview_file(self, file_id: int, max_chars: int = 4000):
        max_chars = min(max(max_chars, 1), 20000)
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")
        if file_code.text is None:
            raise HTTPException(status_code=400, detail="仅文本分享支持预览")

        content = file_code.text
        preview = content[:max_chars]
        return {
            "id": file_code.id,
            "code": file_code.code,
            "name": f"{file_code.prefix}{file_code.suffix}",
            "type": "text",
            "content": preview,
            "length": len(content),
            "previewLength": len(preview),
            "preview_length": len(preview),
            "truncated": len(content) > max_chars,
            "maxChars": max_chars,
            "max_chars": max_chars,
            "createdAt": file_code.created_at,
            "created_at": file_code.created_at,
            "expiredAt": file_code.expired_at,
            "expired_at": file_code.expired_at,
        }

    async def share_local_file(self, item):
        local_file = LocalFileClass(item.filename)
        if not await local_file.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        text = await local_file.read()
        expired_at, expired_count, used_count, code = await get_expire_info(
            item.expire_value, item.expire_style
        )
        path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(item)

        await self.file_storage.save_file(text, save_path)

        await FileCodes.create(
            code=code,
            prefix=prefix,
            suffix=suffix,
            uuid_file_name=uuid_file_name,
            file_path=path,
            size=local_file.size,
            expired_at=expired_at,
            expired_count=expired_count,
            used_count=used_count,
        )

        return {
            "code": code,
            "name": local_file.file,
        }


class ConfigService:
    INT_FIELDS = {
        "enableChunk",
        "errorCount",
        "errorMinute",
        "max_save_seconds",
        "onedrive_proxy",
        "openUpload",
        "port",
        "s3_proxy",
        "serverPort",
        "serverWorkers",
        "showAdminAddr",
        "uploadCount",
        "uploadMinute",
        "uploadSize",
        "webdav_proxy",
    }
    FLOAT_FIELDS = {"opacity"}

    def get_config(self):
        return dict(settings.items())

    async def update_config(self, data: dict):
        current_config = dict(settings.items())
        next_config = dict(current_config)
        update_data = {
            key: value for key, value in data.items() if key in settings.default_config
        }

        admin_token = update_data.get("admin_token")
        if admin_token is None or admin_token == "":
            update_data.pop("admin_token", None)
        elif not is_password_hashed(admin_token):
            update_data["admin_token"] = hash_password(admin_token)

        for key, value in update_data.items():
            if value == "" and key in self.INT_FIELDS | self.FLOAT_FIELDS:
                continue

            try:
                if key in self.INT_FIELDS:
                    next_config[key] = int(value)
                elif key in self.FLOAT_FIELDS:
                    next_config[key] = float(value)
                else:
                    next_config[key] = value
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"{key} 配置值格式错误")

        await KeyValue.update_or_create(key="settings", defaults={"value": next_config})
        await refresh_settings()


class LocalFileService:
    async def list_files(self):
        files = []
        if not os.path.exists(data_root / "local"):
            os.makedirs(data_root / "local")
        for file in os.listdir(data_root / "local"):
            local_file = LocalFileClass(file)
            files.append({
                "file": local_file.file,
                "ctime": local_file.ctime,
                "size": local_file.size,
            })
        return files

    async def delete_file(self, filename: str):
        file = LocalFileClass(filename)
        if await file.exists():
            await file.delete()
            return "删除成功"
        raise HTTPException(status_code=404, detail="文件不存在")


class LocalFileClass:
    def __init__(self, file):
        self.file = file
        self.path = data_root / "local" / file
        if os.path.exists(self.path):
            self.ctime = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(self.path))
            )
            self.size = os.path.getsize(self.path)
        else:
            self.ctime = None
            self.size = None

    async def read(self):
        return open(self.path, "rb")

    async def write(self, data):
        with open(self.path, "w") as f:
            f.write(data)

    async def delete(self):
        os.remove(self.path)

    async def exists(self):
        return os.path.exists(self.path)
