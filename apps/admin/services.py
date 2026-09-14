import asyncio
import hashlib
import io
from pathlib import Path
import os
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Optional

from core.response import APIResponse
from core.storage import FileStorageInterface, StoredFile, storages
from core.settings import (
    ADMIN_SESSION_EXPIRE_MAX,
    ADMIN_SESSION_EXPIRE_MIN,
    settings,
)
from apps.base.config import refresh_settings
from apps.base.services import response_from_download, stored_file_of
from core.security import INTERNAL_CONFIG_KEYS, generate_jwt_secret
from apps.base.models import FileCodes, KeyValue
from apps.base.utils import get_expire_info, get_file_path_name
from apps.base.quota import release_storage, reserve_storage
from fastapi import HTTPException
from core.settings import data_root
from core.utils import get_now, hash_password, is_password_hashed, validate_background_url

# KeyValue 里的 settings/activities/presets 都是整块 JSON 读-改-写；
# 进程内写锁串行化这三个写路径，避免并发管理操作互相覆盖（last-writer-wins）。
# 多进程部署下锁不跨进程——文档已锁定单 worker 部署。
keyvalue_write_lock = asyncio.Lock()


class FileService:
    FILE_METADATA_KEY_PREFIX = "admin_file_metadata:"
    FILE_VIEW_PRESETS_KEY = "admin_file_view_presets"
    ADMIN_ACTIVITY_KEY = "admin_activity_events"
    MAX_METADATA_NOTE_LENGTH = 2000
    MAX_METADATA_TAGS = 12
    MAX_METADATA_TAG_LENGTH = 24
    MAX_VIEW_PRESETS = 24
    MAX_VIEW_PRESET_NAME_LENGTH = 32
    MAX_VIEW_PRESET_KEYWORD_LENGTH = 80
    MAX_ADMIN_ACTIVITIES = 80
    MAX_ADMIN_ACTIVITY_TEXT_LENGTH = 120

    POLICY_ACTIONS = {
        "extend_24h",
        "extend_7d",
        "make_permanent",
        "reset_download_limit",
    }

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
    VIEW_PRESET_STATUS_VALUES = {"all", "active", "expired"}
    VIEW_PRESET_TYPE_VALUES = {"all", "file", "text", "chunked"}
    VIEW_PRESET_HEALTH_VALUES = {
        "all",
        "attention",
        "danger",
        "warning",
        "healthy",
        "expired",
        "expiring_soon",
        "storage_issue",
        "never_retrieved",
        "permanent",
    }
    VIEW_PRESET_SORT_FIELDS = {
        "created_at",
        "expired_at",
        "name",
        "size",
        "used_count",
        "code",
    }

    def __init__(self):
        self._file_storage: Optional[FileStorageInterface] = None

    @property
    def file_storage(self) -> FileStorageInterface:
        if self._file_storage is None:
            self._file_storage = storages[settings.file_storage]()
        return self._file_storage

    def _file_metadata_key(self, file_id: int) -> str:
        return f"{self.FILE_METADATA_KEY_PREFIX}{file_id}"

    async def _delete_file_code(self, file_code: FileCodes):
        if file_code.text is None:
            await self.file_storage.delete_file(stored_file_of(file_code))
        await KeyValue.filter(key=self._file_metadata_key(file_code.id)).delete()
        await file_code.delete()

    async def delete_file(self, file_id: int):
        file_code = await FileCodes.get(id=file_id)
        target_name = self._build_file_activity_name(file_code)
        await self._delete_file_code(file_code)
        await self.record_admin_activity(
            action="file.delete",
            target_type="file",
            target_id=file_id,
            target_name=target_name,
            count=1,
        )

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

        if deleted:
            await self.record_admin_activity(
                action="files.batch_delete",
                target_type="file",
                count=len(deleted),
                meta={
                    "requested_count": len(file_ids),
                    "unique_count": len(unique_ids),
                    "deleted": deleted,
                    "missing": missing,
                    "failed_count": len(failed),
                },
            )

        return {
            "requested_count": len(file_ids),
            "unique_count": len(unique_ids),
            "deleted_count": len(deleted),
            "missing_count": len(missing),
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

        if updated:
            await self.record_admin_activity(
                action="files.batch_update",
                target_type="file",
                count=len(updated),
                meta={
                    "fields": sorted(update_data.keys()),
                    "requested_count": len(file_ids),
                    "unique_count": len(unique_ids),
                    "updated": updated,
                    "missing": missing,
                    "failed_count": len(failed),
                },
            )

        return {
            "requested_count": len(file_ids),
            "unique_count": len(unique_ids),
            "updated_count": len(updated),
            "missing_count": len(missing),
            "failed_count": len(failed),
            "updated": updated,
            "missing": missing,
            "failed": failed,
        }

    async def update_file(
        self,
        file_id: int,
        code: Optional[str] = None,
        prefix: Optional[str] = None,
        suffix: Optional[str] = None,
        expired_at: Optional[Any] = None,
        expired_count: Optional[int] = None,
    ) -> dict[str, Any]:
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")

        update_data: dict[str, Any] = {}
        if code is not None and code != file_code.code:
            if await FileCodes.filter(code=code).first():
                raise HTTPException(status_code=400, detail="code已存在")
            update_data["code"] = code
        if prefix is not None and prefix != file_code.prefix:
            update_data["prefix"] = prefix
        if suffix is not None and suffix != file_code.suffix:
            update_data["suffix"] = suffix
        if expired_at is not None and expired_at != "" and expired_at != file_code.expired_at:
            update_data["expired_at"] = expired_at
        if expired_count is not None and expired_count != file_code.expired_count:
            update_data["expired_count"] = expired_count

        if update_data:
            target_name = self._build_file_activity_name(file_code)
            await file_code.update_from_dict(update_data).save()
            await self.record_admin_activity(
                action="file.update",
                target_type="file",
                target_id=file_id,
                target_name=target_name,
                count=1,
                meta={"fields": sorted(update_data.keys())},
            )
        return {"updated": bool(update_data), "fields": sorted(update_data.keys())}

    async def apply_file_policy_action(
        self,
        file_id: int,
        action: str,
        download_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")

        action = action.strip().lower()
        now = await get_now()
        update_data = self._build_policy_action_update(
            file_code=file_code,
            action=action,
            now=now,
            download_limit=download_limit,
        )

        await file_code.update_from_dict(update_data).save()
        await self.record_admin_activity(
            action="file.policy_action",
            target_type="file",
            target_id=file_id,
            target_name=self._build_file_activity_name(file_code),
            count=1,
            meta={"policy_action": action},
        )
        return await self.get_file_detail(file_id)

    async def get_file_metadata(self, file_id: int) -> dict[str, Any]:
        record = await KeyValue.filter(key=self._file_metadata_key(file_id)).first()
        return self._normalize_file_metadata(record.value if record else None)

    async def update_file_metadata(
        self,
        file_id: int,
        note: Optional[str],
        tags: Optional[list[str]],
        update_note: bool,
        update_tags: bool,
    ) -> dict[str, Any]:
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")

        current_metadata = await self.get_file_metadata(file_id)
        next_metadata = dict(current_metadata)
        if update_note:
            next_metadata["note"] = self._normalize_metadata_note(note)
        if update_tags:
            next_metadata["tags"] = self._normalize_metadata_tags(tags)

        now = await get_now()
        updated_at = now.isoformat()
        next_metadata["updated_at"] = updated_at
        await KeyValue.update_or_create(
            key=self._file_metadata_key(file_id),
            defaults={"value": next_metadata},
        )
        await self.record_admin_activity(
            action="file.metadata_update",
            target_type="file",
            target_id=file_id,
            target_name=self._build_file_activity_name(file_code),
            count=1,
            meta={
                "update_note": update_note,
                "update_tags": update_tags,
                "tag_count": len(next_metadata["tags"]),
            },
        )
        return await self.get_file_detail(file_id)

    async def list_file_view_presets(self) -> dict[str, Any]:
        presets = await self._get_file_view_presets()
        return {
            "presets": presets,
            "total": len(presets),
        }

    async def save_file_view_preset(
        self,
        preset_id: Optional[str],
        name: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        async with keyvalue_write_lock:
            presets = await self._get_file_view_presets()
            normalized_name = self._normalize_file_view_preset_name(name)
            normalized_filters = self._normalize_file_view_preset_filters(filters)
            now = await get_now()
            updated_at = now.isoformat()

            target_index = next(
                (index for index, preset in enumerate(presets) if preset["id"] == preset_id),
                -1,
            )
            is_update = target_index >= 0
            if is_update:
                preset = presets[target_index]
                next_preset = {
                    **preset,
                    "name": normalized_name,
                    "filters": normalized_filters,
                    "updated_at": updated_at,
                }
                presets[target_index] = next_preset
            else:
                if len(presets) >= self.MAX_VIEW_PRESETS:
                    raise HTTPException(status_code=400, detail="视图预设数量已达上限")
                next_preset = {
                    "id": preset_id or self._build_file_view_preset_id(normalized_name, now),
                    "name": normalized_name,
                    "filters": normalized_filters,
                    "created_at": updated_at,
                    "updated_at": updated_at,
                }
                presets.append(next_preset)

            await self._save_file_view_presets(presets)
        await self.record_admin_activity(
            action="file.view_preset_update" if is_update else "file.view_preset_create",
            target_type="view_preset",
            target_id=next_preset["id"],
            target_name=next_preset["name"],
            count=1,
            meta={"filters": normalized_filters},
        )
        return next_preset

    async def delete_file_view_preset(self, preset_id: str) -> dict[str, Any]:
        preset_id = str(preset_id).strip()
        if not preset_id:
            raise HTTPException(status_code=400, detail="请选择要删除的视图预设")

        async with keyvalue_write_lock:
            presets = await self._get_file_view_presets()
            deleted_preset = next(
                (preset for preset in presets if preset["id"] == preset_id),
                None,
            )
            next_presets = [preset for preset in presets if preset["id"] != preset_id]
            if len(next_presets) == len(presets):
                raise HTTPException(status_code=404, detail="视图预设不存在")

            await self._save_file_view_presets(next_presets)
        await self.record_admin_activity(
            action="file.view_preset_delete",
            target_type="view_preset",
            target_id=preset_id,
            target_name=(deleted_preset or {}).get("name", ""),
            count=1,
        )
        return {
            "deleted_preset_id": preset_id,
            "total": len(next_presets),
        }

    async def apply_files_policy_action(
        self,
        file_ids: list[int],
        action: str,
        download_limit: Optional[int] = None,
    ) -> dict[str, Any]:
        unique_ids = list(dict.fromkeys(file_ids))
        updated = []
        failed = []
        missing = []
        action = action.strip().lower()

        if action not in self.POLICY_ACTIONS:
            raise HTTPException(status_code=400, detail="不支持的策略动作")

        if action == "reset_download_limit":
            next_limit = download_limit if download_limit is not None else 5
            if next_limit < 1:
                raise HTTPException(status_code=400, detail="取件次数必须大于 0")

        now = await get_now()
        for file_id in unique_ids:
            file_code = await FileCodes.filter(id=file_id).first()
            if not file_code:
                missing.append(file_id)
                continue

            try:
                update_data = self._build_policy_action_update(
                    file_code=file_code,
                    action=action,
                    now=now,
                    download_limit=download_limit,
                )
                await file_code.update_from_dict(update_data).save()
                updated.append(file_id)
            except Exception as exc:
                failed.append({"id": file_id, "reason": str(exc)})

        if updated:
            await self.record_admin_activity(
                action="files.batch_policy_action",
                target_type="file",
                count=len(updated),
                meta={
                    "policy_action": action,
                    "requested_count": len(file_ids),
                    "unique_count": len(unique_ids),
                    "updated": updated,
                    "missing": missing,
                    "failed_count": len(failed),
                },
            )

        return {
            "requested_count": len(file_ids),
            "unique_count": len(unique_ids),
            "updated_count": len(updated),
            "missing_count": len(missing),
            "failed_count": len(failed),
            "action": action,
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
        health: str = "",
        sort_by: str = "created_at",
        sort_order: str = "desc",
    ):
        page = max(page, 1)
        size = min(max(size, 1), 100)
        keyword = keyword.strip().lower()
        status = status.strip().lower()
        file_type = file_type.strip().lower()
        health = health.strip().lower()
        sort_by = self._normalize_sort_by(sort_by)
        reverse = sort_order.strip().lower() != "asc"

        all_files = await FileCodes.all()
        now = await get_now()
        enriched_files = []
        summary = {
            "total_files": len(all_files),
            "active_count": 0,
            "expired_count": 0,
            "text_count": 0,
            "file_count": 0,
            "chunked_count": 0,
            **self._empty_health_summary(),
            "storage_used": sum(file_code.size for file_code in all_files),
            "used_count": sum(file_code.used_count for file_code in all_files),
        }

        for file_code in all_files:
            item = await self._build_admin_file_item(file_code, now=now)
            if item["is_expired"]:
                summary["expired_count"] += 1
            else:
                summary["active_count"] += 1
            if item["is_text"]:
                summary["text_count"] += 1
            else:
                summary["file_count"] += 1
            if item["is_chunked"]:
                summary["chunked_count"] += 1
            self._accumulate_health_summary(summary, item)

            if not self._match_admin_file(item, keyword, status, file_type, health):
                continue
            enriched_files.append(item)

        enriched_files.sort(
            key=lambda item: self._get_sort_value(item, sort_by),
            reverse=reverse,
        )
        offset = (page - 1) * size
        return enriched_files[offset : offset + size], len(enriched_files), summary

    def _empty_health_summary(self) -> dict[str, int]:
        return {
            "health_attention_count": 0,
            "health_danger_count": 0,
            "health_warning_count": 0,
            "expiring_soon_count": 0,
            "storage_issue_count": 0,
            "never_retrieved_count": 0,
            "healthy_count": 0,
            "permanent_count": 0,
        }

    def _accumulate_health_summary(self, summary: dict[str, Any], item: dict[str, Any]) -> None:
        status_insights = item.get("status_insights") or {}
        reasons = status_insights.get("reasons") or []
        severity = status_insights.get("severity")
        state = status_insights.get("state")

        if severity in {"danger", "warning"}:
            summary["health_attention_count"] += 1
        if severity == "danger":
            summary["health_danger_count"] += 1
        if severity == "warning":
            summary["health_warning_count"] += 1
        if severity == "success":
            summary["healthy_count"] += 1
        if state == "permanent":
            summary["permanent_count"] += 1
        if "expires_soon" in reasons:
            summary["expiring_soon_count"] += 1
        if "storage_metadata_incomplete" in reasons:
            summary["storage_issue_count"] += 1
        if "never_retrieved" in reasons:
            summary["never_retrieved_count"] += 1

    async def build_file_health_summary(
        self, file_codes: list[FileCodes], now: Optional[datetime] = None
    ) -> dict[str, int]:
        if now is None:
            now = await get_now()
        summary = self._empty_health_summary()
        for file_code in file_codes:
            item = await self._build_admin_file_item(file_code, now=now)
            self._accumulate_health_summary(summary, item)
        return summary

    async def _build_admin_file_item(
        self, file_code: FileCodes, now: Optional[datetime] = None
    ) -> dict[str, Any]:
        if now is None:
            now = await get_now()
        is_text = file_code.text is not None
        is_expired = await file_code.is_expired()
        name = f"{file_code.prefix}{file_code.suffix}"
        has_download_limit = file_code.expired_count >= 0
        is_permanent = file_code.expired_at is None and file_code.expired_count < 0
        can_download = is_text or bool(file_code.file_path or file_code.uuid_file_name)
        remaining_downloads = (
            max(file_code.expired_count, 0) if file_code.expired_count >= 0 else None
        )
        data = {
            "id": file_code.id,
            "code": file_code.code,
            "prefix": file_code.prefix,
            "suffix": file_code.suffix,
            "uuid_file_name": file_code.uuid_file_name,
            "file_path": file_code.file_path,
            "size": file_code.size or 0,
            "text": file_code.text,
            "expired_at": file_code.expired_at,
            "expired_count": file_code.expired_count,
            "used_count": file_code.used_count,
            "created_at": file_code.created_at,
            "file_hash": file_code.file_hash,
            "is_chunked": file_code.is_chunked,
            "upload_id": file_code.upload_id,
        }
        data.update(
            {
                "name": name,
                "type": "text" if is_text else "file",
                "status": "expired" if is_expired else "active",
                "is_text": is_text,
                "is_expired": is_expired,
                "is_chunked": file_code.is_chunked,
                "remaining_downloads": remaining_downloads,
                "used_count": file_code.used_count,
                "created_at": file_code.created_at,
                "expired_at": file_code.expired_at,
                "file_hash": file_code.file_hash,
            }
        )
        status_insights = self._build_file_status_insights(
            file_code=file_code,
            detail=data,
            now=now,
            has_download_limit=has_download_limit,
            is_permanent=is_permanent,
            can_download=can_download,
        )
        data.update(
            {
                "status_insights": status_insights,
            }
        )
        return data

    async def get_file_detail(self, file_id: int):
        file_code = await FileCodes.filter(id=file_id).first()
        if not file_code:
            raise HTTPException(status_code=404, detail="文件不存在")

        now = await get_now()
        detail = await self._build_admin_file_item(file_code, now=now)
        is_text = file_code.text is not None
        has_download_limit = file_code.expired_count >= 0
        is_permanent = file_code.expired_at is None and file_code.expired_count < 0
        text_length = len(file_code.text) if file_code.text else 0
        can_download = is_text or bool(file_code.file_path or file_code.uuid_file_name)
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
                "display_name": detail["name"],
                "is_permanent": is_permanent,
                "has_download_limit": has_download_limit,
                "has_expiration_time": file_code.expired_at is not None,
                "text_length": text_length,
                "can_preview_text": is_text,
                "can_download": can_download,
                "storage_backend": settings.file_storage,
                "file_path": file_code.file_path,
                "uuid_file_name": file_code.uuid_file_name,
                "upload_id": file_code.upload_id,
                "policy": {
                    "expired_at": file_code.expired_at,
                    "expired_count": file_code.expired_count,
                    "remaining_downloads": detail["remaining_downloads"],
                    "is_expired": detail["is_expired"],
                    "is_permanent": is_permanent,
                },
                "storage": {
                    "backend": settings.file_storage,
                    "file_path": file_code.file_path,
                    "uuid_file_name": file_code.uuid_file_name,
                    "file_hash": file_code.file_hash,
                    "is_chunked": file_code.is_chunked,
                    "upload_id": file_code.upload_id,
                },
                "status_insights": status_insights,
                "timeline": timeline,
            }
        )
        metadata = await self.get_file_metadata(file_id)
        detail.update(
            {
                "metadata": metadata,
                "note": metadata["note"],
                "tags": metadata["tags"],
                "metadata_updated_at": metadata["updated_at"],
            }
        )
        return detail

    def _normalize_metadata_note(self, note: Optional[str]) -> str:
        if note is None:
            return ""
        return str(note).strip()[: self.MAX_METADATA_NOTE_LENGTH]

    def _normalize_metadata_tags(self, tags: Any) -> list[str]:
        if not tags:
            return []
        if isinstance(tags, str):
            tags = [tags]
        elif not isinstance(tags, list):
            return []

        normalized_tags = []
        seen_tags = set()
        for raw_tag in tags:
            tag = str(raw_tag).strip()
            if not tag:
                continue
            tag = tag[: self.MAX_METADATA_TAG_LENGTH]
            dedupe_key = tag.lower()
            if dedupe_key in seen_tags:
                continue
            seen_tags.add(dedupe_key)
            normalized_tags.append(tag)
            if len(normalized_tags) >= self.MAX_METADATA_TAGS:
                break
        return normalized_tags

    def _normalize_file_metadata(self, metadata: Any) -> dict[str, Any]:
        if not isinstance(metadata, dict):
            metadata = {}

        updated_at = metadata.get("updated_at") or metadata.get("updatedAt")
        return {
            "note": self._normalize_metadata_note(metadata.get("note")),
            "tags": self._normalize_metadata_tags(metadata.get("tags")),
            "updated_at": updated_at,
        }

    async def list_admin_activities(
        self,
        limit: int = 8,
        action: Optional[str] = None,
        target_type: Optional[str] = None,
        keyword: Optional[str] = None,
    ) -> dict[str, Any]:
        try:
            normalized_limit = int(limit or 8)
        except (TypeError, ValueError):
            normalized_limit = 8
        limit = min(max(normalized_limit, 1), self.MAX_ADMIN_ACTIVITIES)
        activities = await self._get_admin_activities()
        normalized_action = self._normalize_admin_activity_text(action).lower()
        normalized_target_type = self._normalize_admin_activity_text(target_type).lower()
        normalized_keyword = self._normalize_admin_activity_text(keyword).lower()
        filtered_activities = self._filter_admin_activities(
            activities,
            action=normalized_action,
            target_type=normalized_target_type,
            keyword=normalized_keyword,
        )
        visible_activities = filtered_activities[:limit]
        action_options = self._build_admin_activity_options(activities, "action")
        target_type_options = self._build_admin_activity_options(activities, "target_type")
        return {
            "activities": visible_activities,
            "total": len(filtered_activities),
            "stored_total": len(activities),
            "limit": limit,
            "filters": {
                "action": normalized_action,
                "target_type": normalized_target_type,
                "keyword": normalized_keyword,
            },
            "action_options": action_options,
            "target_type_options": target_type_options,
        }

    async def record_admin_activity(
        self,
        action: str,
        target_type: str,
        target_id: Optional[Any] = None,
        target_name: str = "",
        count: int = 1,
        meta: Optional[dict[str, Any]] = None,
    ) -> Optional[dict[str, Any]]:
        try:
            now = await get_now()
            created_at = now.isoformat()
            activity = self._normalize_admin_activity(
                {
                    "id": self._build_admin_activity_id(
                        action=action,
                        target_type=target_type,
                        target_id=target_id,
                        target_name=target_name,
                        timestamp=now,
                    ),
                    "action": action,
                    "target_type": target_type,
                    "target_id": target_id,
                    "target_name": target_name,
                    "count": count,
                    "meta": meta or {},
                    "created_at": created_at,
                }
            )
            if not activity:
                return None

            async with keyvalue_write_lock:
                activities = await self._get_admin_activities()
                next_activities = [
                    activity,
                    *[item for item in activities if item["id"] != activity["id"]],
                ][: self.MAX_ADMIN_ACTIVITIES]
                await self._save_admin_activities(next_activities)
            return activity
        except Exception:
            return None

    async def _get_admin_activities(self) -> list[dict[str, Any]]:
        record = await KeyValue.filter(key=self.ADMIN_ACTIVITY_KEY).first()
        raw_activities = record.value if record else []
        if isinstance(raw_activities, dict):
            raw_activities = (
                raw_activities.get("activities") or raw_activities.get("items") or []
            )
        if not isinstance(raw_activities, list):
            return []

        activities = []
        seen_ids = set()
        for raw_activity in raw_activities:
            activity = self._normalize_admin_activity(raw_activity)
            if not activity or activity["id"] in seen_ids:
                continue
            seen_ids.add(activity["id"])
            activities.append(activity)
            if len(activities) >= self.MAX_ADMIN_ACTIVITIES:
                break

        activities.sort(key=lambda item: item.get("created_at") or "", reverse=True)
        return activities

    async def _save_admin_activities(self, activities: list[dict[str, Any]]) -> None:
        await KeyValue.update_or_create(
            key=self.ADMIN_ACTIVITY_KEY,
            defaults={"value": {"activities": activities}},
        )

    def _normalize_admin_activity(self, activity: Any) -> Optional[dict[str, Any]]:
        if not isinstance(activity, dict):
            return None

        action = self._normalize_admin_activity_text(activity.get("action"))
        target_type = self._normalize_admin_activity_text(
            activity.get("target_type") or activity.get("targetType") or "system"
        )
        if not action:
            return None

        target_name = self._normalize_admin_activity_text(
            activity.get("target_name") or activity.get("targetName")
        )
        created_at = activity.get("created_at") or activity.get("createdAt")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        created_at = str(created_at or "")
        if not created_at:
            return None

        target_id = activity.get("target_id")
        if target_id is None:
            target_id = activity.get("targetId")

        count = activity.get("count", 1)
        try:
            count = max(int(count), 1)
        except (TypeError, ValueError):
            count = 1

        meta = activity.get("meta")
        if not isinstance(meta, dict):
            meta = {}

        activity_id = self._normalize_admin_activity_text(activity.get("id"))
        if not activity_id:
            activity_id = self._build_admin_activity_id(
                action=action,
                target_type=target_type,
                target_id=target_id,
                target_name=target_name,
                timestamp=None,
                seed=created_at,
            )

        return {
            "id": activity_id,
            "action": action,
            "target_type": target_type,
            "target_id": target_id,
            "target_name": target_name,
            "count": count,
            "meta": meta,
            "created_at": created_at,
        }

    def _normalize_admin_activity_text(self, value: Any) -> str:
        return str(value or "").strip()[: self.MAX_ADMIN_ACTIVITY_TEXT_LENGTH]

    def _filter_admin_activities(
        self,
        activities: list[dict[str, Any]],
        action: str,
        target_type: str,
        keyword: str,
    ) -> list[dict[str, Any]]:
        filtered_activities = []
        for activity in activities:
            if action and str(activity.get("action") or "").lower() != action:
                continue
            if target_type and str(activity.get("target_type") or "").lower() != target_type:
                continue
            if keyword and not self._activity_matches_keyword(activity, keyword):
                continue
            filtered_activities.append(activity)
        return filtered_activities

    def _activity_matches_keyword(self, activity: dict[str, Any], keyword: str) -> bool:
        searchable_values = [
            activity.get("action"),
            activity.get("target_type"),
            activity.get("target_type"),
            activity.get("target_id"),
            activity.get("target_id"),
            activity.get("target_name"),
            activity.get("target_name"),
        ]
        meta = activity.get("meta")
        if isinstance(meta, dict):
            searchable_values.extend(meta.values())

        return any(keyword in str(value or "").lower() for value in searchable_values)

    def _build_admin_activity_options(
        self,
        activities: list[dict[str, Any]],
        field: str,
    ) -> list[dict[str, Any]]:
        counters: dict[str, dict[str, Any]] = {}
        for activity in activities:
            raw_value = self._normalize_admin_activity_text(activity.get(field))
            if not raw_value:
                continue
            value = raw_value.lower()
            if value not in counters:
                counters[value] = {"label": raw_value, "count": 0}
            counters[value]["count"] += 1

        return [
            {
                "value": value,
                "label": option["label"],
                "count": option["count"],
            }
            for value, option in sorted(
                counters.items(),
                key=lambda item: (-item[1]["count"], item[0]),
            )
        ]

    def _build_admin_activity_id(
        self,
        action: str,
        target_type: str,
        target_id: Optional[Any],
        target_name: str,
        timestamp: Optional[datetime],
        seed: Optional[str] = None,
    ) -> str:
        timestamp_seed = (
            str(int(timestamp.timestamp() * 1000)) if timestamp else str(seed or "activity")
        )
        digest = hashlib.sha1(
            f"{timestamp_seed}:{action}:{target_type}:{target_id}:{target_name}".encode("utf-8")
        ).hexdigest()[:10]
        return f"act_{timestamp_seed}_{digest}"

    def _build_file_activity_name(self, file_code: FileCodes) -> str:
        return (file_code.prefix + file_code.suffix) or file_code.code

    async def _get_file_view_presets(self) -> list[dict[str, Any]]:
        record = await KeyValue.filter(key=self.FILE_VIEW_PRESETS_KEY).first()
        raw_presets = record.value if record else []
        if isinstance(raw_presets, dict):
            raw_presets = raw_presets.get("presets") or raw_presets.get("items") or []
        if not isinstance(raw_presets, list):
            return []

        presets = []
        seen_ids = set()
        for raw_preset in raw_presets:
            try:
                preset = self._normalize_file_view_preset(raw_preset)
            except HTTPException:
                continue
            if not preset or preset["id"] in seen_ids:
                continue
            seen_ids.add(preset["id"])
            presets.append(preset)
            if len(presets) >= self.MAX_VIEW_PRESETS:
                break
        return presets

    async def _save_file_view_presets(self, presets: list[dict[str, Any]]) -> None:
        await KeyValue.update_or_create(
            key=self.FILE_VIEW_PRESETS_KEY,
            defaults={"value": {"presets": presets}},
        )

    def _normalize_file_view_preset(self, preset: Any) -> Optional[dict[str, Any]]:
        if not isinstance(preset, dict):
            return None

        preset_id = str(preset.get("id") or "").strip()
        raw_name = str(preset.get("name") or "").strip()
        if not raw_name:
            return None
        name = self._normalize_file_view_preset_name(raw_name)
        if not preset_id:
            preset_id = self._build_file_view_preset_id(name)

        filters = preset.get("filters") or preset.get("params") or {}
        normalized_filters = self._normalize_file_view_preset_filters(filters)
        created_at = preset.get("created_at")
        updated_at = preset.get("updated_at") or preset.get("updatedAt")

        return {
            "id": preset_id,
            "name": name,
            "filters": normalized_filters,
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def _normalize_file_view_preset_name(self, name: Any) -> str:
        normalized_name = str(name or "").strip()
        if not normalized_name:
            raise HTTPException(status_code=400, detail="请输入视图名称")
        return normalized_name[: self.MAX_VIEW_PRESET_NAME_LENGTH]

    def _normalize_file_view_preset_filters(self, filters: Any) -> dict[str, Any]:
        if not isinstance(filters, dict):
            filters = {}

        sort_by = str(filters.get("sortBy") or filters.get("sort_by") or "created_at")
        sort_by = sort_by.replace("-", "_").strip().lower()
        if sort_by not in self.VIEW_PRESET_SORT_FIELDS:
            sort_by = "created_at"

        sort_order = str(filters.get("sortOrder") or filters.get("sort_order") or "desc")
        sort_order = sort_order.strip().lower()
        if sort_order not in {"asc", "desc"}:
            sort_order = "desc"

        size = filters.get("size", 10)
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 10

        return {
            "keyword": str(filters.get("keyword") or "").strip()[
                : self.MAX_VIEW_PRESET_KEYWORD_LENGTH
            ],
            "status": self._normalize_file_view_preset_choice(
                filters.get("status"), self.VIEW_PRESET_STATUS_VALUES
            ),
            "type": self._normalize_file_view_preset_choice(
                filters.get("type"), self.VIEW_PRESET_TYPE_VALUES
            ),
            "health": self._normalize_file_view_preset_choice(
                filters.get("health"), self.VIEW_PRESET_HEALTH_VALUES
            ),
            "sort_by": sort_by,
            "sort_order": sort_order,
            "size": min(max(size, 1), 100),
        }

    def _normalize_file_view_preset_choice(self, value: Any, allowed_values: set[str]) -> str:
        normalized_value = str(value or "all").strip().lower()
        if normalized_value not in allowed_values:
            return "all"
        return normalized_value

    def _build_file_view_preset_id(
        self, name: str, timestamp: Optional[datetime] = None
    ) -> str:
        seed = int(timestamp.timestamp() * 1000) if timestamp else "saved"
        digest = hashlib.sha1(name.encode("utf-8")).hexdigest()[:8]
        return f"view_{seed}_{digest}"

    def _build_file_status_insights(
        self,
        file_code: FileCodes,
        detail: dict[str, Any],
        now: datetime,
        has_download_limit: bool,
        is_permanent: bool,
        can_download: bool,
    ) -> dict[str, Any]:
        remaining_downloads = detail["remaining_downloads"]
        seconds_until_expiration = self._seconds_between(now, file_code.expired_at)
        age_seconds = self._seconds_between(file_code.created_at, now)
        reasons = []

        if detail["is_expired"]:
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
        if detail["is_expired"] or (has_download_limit and remaining_downloads == 0):
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
            "next_action": next_action,
            "reasons": reasons,
            "metrics": {
                "age_seconds": max(age_seconds or 0, 0),
                "seconds_until_expiration": seconds_until_expiration,
                "remaining_downloads": remaining_downloads,
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
        remaining_downloads = detail["remaining_downloads"]
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

    def _build_policy_action_update(
        self,
        file_code: FileCodes,
        action: str,
        now: datetime,
        download_limit: Optional[int],
    ) -> dict[str, Any]:
        if action == "extend_24h":
            return {"expired_at": self._extended_expiration(file_code.expired_at, now, hours=24)}
        if action == "extend_7d":
            return {"expired_at": self._extended_expiration(file_code.expired_at, now, days=7)}
        if action == "make_permanent":
            return {"expired_at": None, "expired_count": -1}
        if action == "reset_download_limit":
            next_limit = download_limit if download_limit is not None else 5
            if next_limit < 1:
                raise HTTPException(status_code=400, detail="取件次数必须大于 0")
            return {"expired_count": next_limit}

        raise HTTPException(status_code=400, detail="不支持的策略动作")

    def _extended_expiration(
        self,
        expired_at: Optional[datetime],
        now: datetime,
        **duration: int,
    ) -> datetime:
        base_time = now
        if expired_at is not None:
            comparable_expired_at = self._align_datetime(expired_at, now)
            if comparable_expired_at > now:
                base_time = comparable_expired_at
        return base_time + timedelta(**duration)

    def _align_datetime(self, value: datetime, reference: datetime) -> datetime:
        if value.tzinfo is None and reference.tzinfo is not None:
            return value.replace(tzinfo=reference.tzinfo)
        if value.tzinfo is not None and reference.tzinfo is None:
            return value.replace(tzinfo=None)
        return value

    def _match_admin_file(
        self,
        item: dict[str, Any],
        keyword: str,
        status: str,
        file_type: str,
        health: str,
    ) -> bool:
        if status == "active" and item["is_expired"]:
            return False
        if status == "expired" and not item["is_expired"]:
            return False
        if file_type == "text" and not item["is_text"]:
            return False
        if file_type == "file" and item["is_text"]:
            return False
        if file_type == "chunked" and not item["is_chunked"]:
            return False
        if not self._match_admin_file_health(item, health):
            return False
        if not keyword:
            return True

        search_values = [
            item.get("code"),
            item.get("name"),
            item.get("prefix"),
            item.get("suffix"),
            item.get("file_hash"),
            item.get("text"),
        ]
        return any(keyword in str(value).lower() for value in search_values if value)

    def _match_admin_file_health(self, item: dict[str, Any], health: str) -> bool:
        if not health or health == "all":
            return True

        status_insights = item.get("status_insights") or {}
        severity = status_insights.get("severity")
        state = status_insights.get("state")
        reasons = set(status_insights.get("reasons") or [])

        if health == "attention":
            return severity in {"danger", "warning"}
        if health == "danger":
            return severity == "danger"
        if health == "warning":
            return severity == "warning"
        if health == "expired":
            return state == "expired" or item.get("is_expired") is True
        if health == "expiring_soon":
            return "expires_soon" in reasons
        if health == "storage_issue":
            return state == "storage_incomplete" or "storage_metadata_incomplete" in reasons
        if health == "never_retrieved":
            return "never_retrieved" in reasons
        if health == "healthy":
            return severity == "success"
        if health == "permanent":
            return state == "permanent"

        return True

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
            "created_at": date_value(item.get("created_at")),
            "createdat": date_value(item.get("created_at")),
            "expired_at": date_value(item.get("expired_at")),
            "expiredat": date_value(item.get("expired_at")),
            "name": item.get("name") or "",
            "size": item.get("size") or 0,
            "used_count": item.get("used_count") or 0,
            "usedcount": item.get("used_count") or 0,
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
            return response_from_download(await self.file_storage.get_file_response(stored_file_of(file_code)))

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
            "preview_length": len(preview),
            "truncated": len(content) > max_chars,
            "max_chars": max_chars,
            "created_at": file_code.created_at,
            "expired_at": file_code.expired_at,
        }

    async def share_local_file(self, item):
        local_file = LocalFileClass(item.filename)
        if not await local_file.exists():
            raise HTTPException(status_code=404, detail="文件不存在")

        reservation_token = f"local:{uuid.uuid4().hex}"
        await reserve_storage(reservation_token, local_file.size, ttl_seconds=3600)
        try:
            data = await local_file.read()  # bytes（read 内部用 with 关闭句柄）
            expired_at, expired_count, used_count, code = await get_expire_info(
                item.expire_value, item.expire_style
            )
            path, suffix, prefix, uuid_file_name, save_path = await get_file_path_name(
                item
            )
            await self.file_storage.save_file(io.BytesIO(data), save_path)
            try:
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
            except Exception:
                await self.file_storage.delete_file(
                    StoredFile(file_path=path, uuid_file_name=uuid_file_name)
                )
                raise
        finally:
            await release_storage(reservation_token)

        return {
            "code": code,
            "name": local_file.file,
        }


class ConfigService:
    INT_FIELDS = {
        "admin_session_expire",
        "enable_chunk",
        "error_count",
        "error_minute",
        "login_count",
        "login_minute",
        "max_save_seconds",
        "onedrive_proxy",
        "open_upload",
        "port",
        "s3_proxy",
        "server_port",
        "server_workers",
        "show_admin_addr",
        "storage_limit",
        "upload_count",
        "upload_minute",
        "upload_size",
        "webdav_proxy",
    }
    FLOAT_FIELDS = {"opacity"}

    def get_config(self):
        config = dict(settings.items())
        config["admin_token"] = ""
        for key in INTERNAL_CONFIG_KEYS:
            config.pop(key, None)
        return config

    async def update_config(self, data: dict):
        current_config = dict(settings.items())
        next_config = dict(current_config)
        update_data = {
            key: value
            for key, value in data.items()
            if key in settings.default_config and key not in INTERNAL_CONFIG_KEYS
        }

        admin_token = update_data.get("admin_token")
        admin_password_changed = False
        if admin_token is None or admin_token == "":
            update_data.pop("admin_token", None)
        elif not is_password_hashed(admin_token):
            update_data["admin_token"] = hash_password(admin_token)
            admin_password_changed = True
        else:
            admin_password_changed = True

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

        try:
            session_expire = int(next_config.get("admin_session_expire"))
        except (TypeError, ValueError):
            raise HTTPException(
                status_code=400,
                detail="admin_session_expire 配置值格式错误",
            )
        if (
            not ADMIN_SESSION_EXPIRE_MIN <= session_expire <= ADMIN_SESSION_EXPIRE_MAX
            or session_expire % ADMIN_SESSION_EXPIRE_MIN != 0
        ):
            raise HTTPException(
                status_code=400,
                detail="admin_session_expire 必须是 1 到 365 个整天",
            )
        next_config["admin_session_expire"] = session_expire

        if int(next_config.get("storage_limit", 0)) < 0:
            raise HTTPException(
                status_code=400,
                detail="storage_limit 不能小于 0",
            )

        # 只校验"发生变化"的值：升级前存入的旧格式 background（相对路径、含空格
        # 或括号）在旧版本是合法的，若每次保存都重新校验，存量部署会连无关设置项
        # 都保存不了（一律 400）。渲染侧仍然 html 转义，而任何修改都必须通过校验。
        current_background = str(settings.background or "")
        candidate_background = str(next_config.get("background") or "")
        if candidate_background != current_background:
            try:
                validate_background_url(candidate_background)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        if admin_password_changed:
            next_config["jwt_secret"] = generate_jwt_secret()

        async with keyvalue_write_lock:
            await KeyValue.update_or_create(key="settings", defaults={"value": next_config})
        await refresh_settings(force=True)


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
        # 仅允许 data/local 目录下的单层文件名，阻断路径穿越与绝对路径访问。
        raw_name = str(file or "")
        normalized = Path(raw_name).as_posix()
        # 输入本身不得包含路径分隔符或绝对路径形态。
        if (
            not raw_name
            or raw_name in {".", ".."}
            or normalized in {".", ".."}
            or "/" in normalized
            or normalized.startswith("~")
            or Path(raw_name).is_absolute()
            or Path(raw_name).name != raw_name
        ):
            raise HTTPException(status_code=400, detail="非法文件名")

        safe_name = Path(raw_name).name
        if not safe_name or safe_name in {".", ".."}:
            raise HTTPException(status_code=400, detail="非法文件名")

        local_root = (data_root / "local").resolve()
        candidate = (local_root / safe_name).resolve()
        try:
            candidate.relative_to(local_root)
        except ValueError:
            raise HTTPException(status_code=400, detail="非法文件路径")

        self.file = safe_name
        self.path = candidate
        if self.path.is_file():
            self.ctime = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(os.path.getctime(self.path))
            )
            self.size = os.path.getsize(self.path)
        else:
            self.ctime = None
            self.size = None

    async def read(self) -> bytes:
        with open(self.path, "rb") as fh:
            return fh.read()

    async def write(self, data):
        with open(self.path, "w") as f:
            f.write(data)

    async def delete(self):
        os.remove(self.path)

    async def exists(self):
        return self.path.is_file()
