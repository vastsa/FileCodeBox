import hashlib
import os
import time
from datetime import datetime, timedelta
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
            await self.file_storage.delete_file(file_code)
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
                    "requestedCount": len(file_ids),
                    "uniqueCount": len(unique_ids),
                    "deleted": deleted,
                    "missing": missing,
                    "failedCount": len(failed),
                },
            )

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

        if updated:
            await self.record_admin_activity(
                action="files.batch_update",
                target_type="file",
                count=len(updated),
                meta={
                    "fields": sorted(update_data.keys()),
                    "requestedCount": len(file_ids),
                    "uniqueCount": len(unique_ids),
                    "updated": updated,
                    "missing": missing,
                    "failedCount": len(failed),
                },
            )

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
            meta={"policyAction": action},
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
        next_metadata["updatedAt"] = updated_at
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
                "updateNote": update_note,
                "updateTags": update_tags,
                "tagCount": len(next_metadata["tags"]),
            },
        )
        return await self.get_file_detail(file_id)

    async def list_file_view_presets(self) -> dict[str, Any]:
        presets = await self._get_file_view_presets()
        return {
            "presets": presets,
            "items": presets,
            "total": len(presets),
        }

    async def save_file_view_preset(
        self,
        preset_id: Optional[str],
        name: str,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
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
                "params": normalized_filters,
                "updatedAt": updated_at,
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
                "params": normalized_filters,
                "createdAt": updated_at,
                "created_at": updated_at,
                "updatedAt": updated_at,
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
            "deleted": preset_id,
            "deletedPresetId": preset_id,
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
                    "policyAction": action,
                    "requestedCount": len(file_ids),
                    "uniqueCount": len(unique_ids),
                    "updated": updated,
                    "missing": missing,
                    "failedCount": len(failed),
                },
            )

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
        status = self._normalize_file_view_preset_choice(
            status, self.VIEW_PRESET_STATUS_VALUES
        )
        file_type = self._normalize_file_view_preset_choice(
            file_type, self.VIEW_PRESET_TYPE_VALUES
        )
        health = self._normalize_file_view_preset_choice(
            health, self.VIEW_PRESET_HEALTH_VALUES
        )
        sort_by = self._normalize_sort_by(sort_by)
        reverse = sort_order.strip().lower() != "asc"

        all_files = await FileCodes.all()
        now = await get_now()
        enriched_files = []
        summary = {
            "totalFiles": len(all_files),
            "activeCount": 0,
            "expiredCount": 0,
            "textCount": 0,
            "fileCount": 0,
            "chunkedCount": 0,
            **self._empty_health_summary(),
            "storageUsed": sum(file_code.size for file_code in all_files),
            "usedCount": sum(file_code.used_count for file_code in all_files),
        }

        for file_code in all_files:
            item = await self._build_admin_file_item(file_code, now=now)
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
            self._accumulate_health_summary(summary, item)

            if not self._match_admin_file(item, keyword, status, file_type, health):
                continue
            enriched_files.append(item)

        enriched_files.sort(
            key=lambda item: self._get_sort_value(item, sort_by),
            reverse=reverse,
        )
        view_summary = self._build_file_view_summary(
            files=enriched_files,
            all_file_count=len(all_files),
            filters={
                "keyword": keyword,
                "status": status or "all",
                "type": file_type or "all",
                "health": health or "all",
                "sortBy": sort_by,
                "sort_by": sort_by,
                "sortOrder": "desc" if reverse else "asc",
                "sort_order": "desc" if reverse else "asc",
            },
        )
        offset = (page - 1) * size
        return (
            enriched_files[offset : offset + size],
            len(enriched_files),
            summary,
            view_summary,
        )

    def _empty_health_summary(self) -> dict[str, int]:
        return {
            "healthAttentionCount": 0,
            "healthDangerCount": 0,
            "healthWarningCount": 0,
            "expiringSoonCount": 0,
            "storageIssueCount": 0,
            "neverRetrievedCount": 0,
            "healthyCount": 0,
            "permanentCount": 0,
        }

    def _accumulate_health_summary(self, summary: dict[str, Any], item: dict[str, Any]) -> None:
        status_insights = item.get("statusInsights") or {}
        reasons = status_insights.get("reasons") or []
        severity = status_insights.get("severity")
        state = status_insights.get("state")

        if severity in {"danger", "warning"}:
            summary["healthAttentionCount"] += 1
        if severity == "danger":
            summary["healthDangerCount"] += 1
        if severity == "warning":
            summary["healthWarningCount"] += 1
        if severity == "success":
            summary["healthyCount"] += 1
        if state == "permanent":
            summary["permanentCount"] += 1
        if "expires_soon" in reasons:
            summary["expiringSoonCount"] += 1
        if "storage_metadata_incomplete" in reasons:
            summary["storageIssueCount"] += 1
        if "never_retrieved" in reasons:
            summary["neverRetrievedCount"] += 1

    def _build_file_view_summary(
        self,
        files: list[dict[str, Any]],
        all_file_count: int,
        filters: dict[str, Any],
    ) -> dict[str, Any]:
        view_counts = {
            "totalFiles": len(files),
            "activeCount": 0,
            "expiredCount": 0,
            "textCount": 0,
            "fileCount": 0,
            "chunkedCount": 0,
            **self._empty_health_summary(),
            "storageUsed": sum(item.get("size") or 0 for item in files),
            "usedCount": sum(item.get("usedCount") or 0 for item in files),
        }

        for item in files:
            if item.get("isExpired"):
                view_counts["expiredCount"] += 1
            else:
                view_counts["activeCount"] += 1
            if item.get("isText"):
                view_counts["textCount"] += 1
            else:
                view_counts["fileCount"] += 1
            if item.get("isChunked"):
                view_counts["chunkedCount"] += 1
            self._accumulate_health_summary(view_counts, item)

        cards = self._build_file_view_summary_cards(view_counts)
        actions = self._build_file_view_summary_actions(cards)
        strongest_severity = self._get_strongest_summary_severity(cards)
        active_filter_count = sum(
            [
                1 if str(filters.get("keyword") or "").strip() else 0,
                1 if str(filters.get("status") or "all").strip() != "all" else 0,
                1 if str(filters.get("type") or "all").strip() != "all" else 0,
                1 if str(filters.get("health") or "all").strip() != "all" else 0,
            ]
        )

        return {
            "total": len(files),
            "filteredTotal": len(files),
            "filtered_total": len(files),
            "allTotal": max(int(all_file_count or 0), 0),
            "all_total": max(int(all_file_count or 0), 0),
            "activeFilterCount": active_filter_count,
            "active_filter_count": active_filter_count,
            "hasFilters": active_filter_count > 0,
            "has_filters": active_filter_count > 0,
            "strongestSeverity": strongest_severity,
            "strongest_severity": strongest_severity,
            "filters": filters,
            "summary": view_counts,
            "healthSummary": view_counts,
            "health_summary": view_counts,
            "cards": cards,
            "items": cards,
            "actions": actions,
        }

    def _build_file_view_summary_cards(
        self, summary: dict[str, Any]
    ) -> list[dict[str, Any]]:
        candidates = [
            {
                "key": "storage_issue",
                "severity": "danger",
                "priority": 100,
                "count": summary["storageIssueCount"],
                "health": "storage_issue",
            },
            {
                "key": "expired",
                "severity": "danger" if summary["expiredCount"] >= 10 else "warning",
                "priority": 90,
                "count": summary["expiredCount"],
                "health": "expired",
            },
            {
                "key": "expiring_soon",
                "severity": "warning",
                "priority": 80,
                "count": summary["expiringSoonCount"],
                "health": "expiring_soon",
            },
            {
                "key": "never_retrieved",
                "severity": "neutral",
                "priority": 60,
                "count": summary["neverRetrievedCount"],
                "health": "never_retrieved",
            },
            {
                "key": "permanent",
                "severity": "neutral",
                "priority": 40,
                "count": summary["permanentCount"],
                "health": "permanent",
            },
        ]
        cards = [
            self._build_file_view_summary_item(
                key=item["key"],
                severity=item["severity"],
                priority=item["priority"],
                count=item["count"],
                health=item["health"],
            )
            for item in candidates
            if item["count"] > 0
        ]

        if not cards:
            key = "empty" if summary["totalFiles"] == 0 else "healthy"
            cards.append(
                self._build_file_view_summary_item(
                    key=key,
                    severity="success" if summary["totalFiles"] > 0 else "neutral",
                    priority=10,
                    count=summary["totalFiles"],
                    health="healthy" if summary["totalFiles"] > 0 else "all",
                )
            )

        cards.sort(key=lambda item: (-item["priority"], item["key"]))
        return cards[:4]

    def _build_file_view_summary_actions(
        self, cards: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        action_key_map = {
            "storage_issue": "inspect_storage",
            "expired": "cleanup_expired",
            "expiring_soon": "extend_expiring",
            "never_retrieved": "review_never_retrieved",
            "permanent": "review_permanent",
            "healthy": "monitor",
            "empty": "clear_filters",
        }
        return [
            {
                **item,
                "sourceKey": item["key"],
                "source_key": item["key"],
                "suggestedAction": action_key_map.get(item["key"], "review"),
                "suggested_action": action_key_map.get(item["key"], "review"),
            }
            for item in cards
            if item["severity"] != "success"
        ]

    def _build_file_view_summary_item(
        self,
        key: str,
        severity: str,
        priority: int,
        count: int,
        health: str,
    ) -> dict[str, Any]:
        return {
            "key": key,
            "severity": severity,
            "priority": priority,
            "count": max(int(count or 0), 0),
            "actionType": "filter",
            "action_type": "filter",
            "health": health,
            "targetHealth": health,
            "target_health": health,
        }

    def _get_strongest_summary_severity(self, items: list[dict[str, Any]]) -> str:
        severity_order = {"danger": 3, "warning": 2, "neutral": 1, "success": 0}
        return max(
            (item["severity"] for item in items),
            key=lambda severity: severity_order.get(severity, 0),
            default="success",
        )

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

    async def get_dashboard_maintenance_queue(self) -> dict[str, Any]:
        file_codes = await FileCodes.all()
        now = await get_now()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_size = sum(
            file_code.size
            for file_code in file_codes
            if file_code.created_at and file_code.created_at >= today_start
        )
        expired_count = 0
        for file_code in file_codes:
            if await file_code.is_expired():
                expired_count += 1

        health_summary = await self.build_file_health_summary(file_codes, now=now)
        return self.build_dashboard_maintenance_queue(
            health_summary=health_summary,
            total_files=len(file_codes),
            expired_count=expired_count,
            today_size=today_size,
            upload_size_limit=settings.uploadSize,
            open_upload=settings.openUpload,
            enable_chunk=settings.enableChunk,
            max_save_seconds=settings.max_save_seconds,
        )

    def build_dashboard_operational_insights(
        self,
        health_summary: dict[str, int],
        total_files: int,
        expired_count: int,
        today_size: int,
        upload_size_limit: int,
        open_upload: int,
        enable_chunk: int,
        max_save_seconds: int,
    ) -> list[dict[str, Any]]:
        def to_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        total_files = to_int(total_files)
        expired_count = to_int(expired_count)
        today_size = to_int(today_size)
        upload_size_limit = to_int(upload_size_limit)
        open_upload = to_int(open_upload)
        enable_chunk = to_int(enable_chunk)
        max_save_seconds = to_int(max_save_seconds)
        insights = []

        if health_summary.get("storageIssueCount", 0) > 0:
            insights.append(
                self._build_dashboard_operational_insight(
                    key="storage_issue",
                    severity="danger",
                    priority=100,
                    count=health_summary["storageIssueCount"],
                    action_type="file_queue",
                    health="storage_issue",
                )
            )

        if expired_count > 0:
            insights.append(
                self._build_dashboard_operational_insight(
                    key="expired_cleanup",
                    severity="danger" if expired_count >= 10 else "warning",
                    priority=90,
                    count=expired_count,
                    action_type="file_queue",
                    health="expired",
                )
            )

        if health_summary.get("expiringSoonCount", 0) > 0:
            insights.append(
                self._build_dashboard_operational_insight(
                    key="expiring_soon",
                    severity="warning",
                    priority=80,
                    count=health_summary["expiringSoonCount"],
                    action_type="file_queue",
                    health="expiring_soon",
                )
            )

        never_retrieved_count = health_summary.get("neverRetrievedCount", 0)
        if total_files > 0 and never_retrieved_count >= max(3, total_files // 5):
            insights.append(
                self._build_dashboard_operational_insight(
                    key="never_retrieved",
                    severity="neutral",
                    priority=60,
                    count=never_retrieved_count,
                    action_type="file_queue",
                    health="never_retrieved",
                )
            )

        if open_upload and max_save_seconds <= 0:
            insights.append(
                self._build_dashboard_operational_insight(
                    key="guest_upload_retention",
                    severity="warning",
                    priority=50,
                    count=1,
                    action_type="settings",
                )
            )

        if (
            upload_size_limit > 0
            and today_size >= upload_size_limit
            and not enable_chunk
        ):
            insights.append(
                self._build_dashboard_operational_insight(
                    key="chunking_disabled",
                    severity="neutral",
                    priority=40,
                    count=1,
                    action_type="settings",
                )
            )

        if not insights:
            insights.append(
                self._build_dashboard_operational_insight(
                    key="healthy",
                    severity="success",
                    priority=10,
                    count=total_files,
                    action_type="file_queue",
                    health="healthy",
                )
            )

        insights.sort(key=lambda item: (-item["priority"], item["key"]))
        return insights[:4]

    def build_dashboard_maintenance_queue(
        self,
        health_summary: dict[str, int],
        total_files: int,
        expired_count: int,
        today_size: int,
        upload_size_limit: int,
        open_upload: int,
        enable_chunk: int,
        max_save_seconds: int,
    ) -> dict[str, Any]:
        def to_int(value: Any) -> int:
            try:
                return int(value or 0)
            except (TypeError, ValueError):
                return 0

        total_files = to_int(total_files)
        expired_count = to_int(expired_count)
        today_size = to_int(today_size)
        upload_size_limit = to_int(upload_size_limit)
        open_upload = to_int(open_upload)
        enable_chunk = to_int(enable_chunk)
        max_save_seconds = to_int(max_save_seconds)
        items = []

        if health_summary.get("storageIssueCount", 0) > 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="storage_issue",
                    severity="danger",
                    category="storage",
                    priority=100,
                    count=health_summary["storageIssueCount"],
                    action_type="file_queue",
                    health="storage_issue",
                    suggested_action="inspect_storage",
                )
            )

        if expired_count > 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="expired_cleanup",
                    severity="danger" if expired_count >= 10 else "warning",
                    category="retention",
                    priority=90,
                    count=expired_count,
                    action_type="file_queue",
                    health="expired",
                    suggested_action="cleanup_or_extend",
                )
            )

        if health_summary.get("expiringSoonCount", 0) > 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="expiring_soon",
                    severity="warning",
                    category="retention",
                    priority=80,
                    count=health_summary["expiringSoonCount"],
                    action_type="file_queue",
                    health="expiring_soon",
                    suggested_action="extend_expiration",
                )
            )

        never_retrieved_count = health_summary.get("neverRetrievedCount", 0)
        if never_retrieved_count > 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="never_retrieved",
                    severity="neutral",
                    category="adoption",
                    priority=60,
                    count=never_retrieved_count,
                    action_type="file_queue",
                    health="never_retrieved",
                    suggested_action="review_usage",
                )
            )

        permanent_count = health_summary.get("permanentCount", 0)
        if permanent_count > 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="permanent_review",
                    severity="neutral",
                    category="retention",
                    priority=45,
                    count=permanent_count,
                    action_type="file_queue",
                    health="permanent",
                    suggested_action="review_retention",
                )
            )

        if open_upload and max_save_seconds <= 0:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="guest_upload_retention",
                    severity="warning",
                    category="settings",
                    priority=70,
                    count=1,
                    action_type="settings",
                    suggested_action="set_retention_limit",
                )
            )

        if (
            upload_size_limit > 0
            and today_size >= upload_size_limit
            and not enable_chunk
        ):
            items.append(
                self._build_dashboard_maintenance_item(
                    key="chunking_disabled",
                    severity="neutral",
                    category="settings",
                    priority=40,
                    count=1,
                    action_type="settings",
                    suggested_action="enable_chunking",
                )
            )

        if not items:
            items.append(
                self._build_dashboard_maintenance_item(
                    key="healthy",
                    severity="success",
                    category="system",
                    priority=10,
                    count=total_files,
                    action_type="file_queue",
                    health="healthy",
                    suggested_action="monitor",
                )
            )

        items.sort(key=lambda item: (-item["priority"], item["key"]))
        summary = self._build_dashboard_maintenance_summary(items)
        return {
            "items": items,
            "maintenanceItems": items,
            "maintenance_items": items,
            "summary": summary,
            "maintenanceSummary": summary,
            "maintenance_summary": summary,
        }

    def _build_dashboard_maintenance_item(
        self,
        key: str,
        severity: str,
        category: str,
        priority: int,
        count: int,
        action_type: str,
        suggested_action: str,
        health: Optional[str] = None,
    ) -> dict[str, Any]:
        action = {
            "type": action_type,
            "actionType": action_type,
            "action_type": action_type,
            "suggestedAction": suggested_action,
            "suggested_action": suggested_action,
        }
        if health:
            action.update(
                {
                    "health": health,
                    "targetHealth": health,
                    "target_health": health,
                }
            )

        return {
            "key": key,
            "severity": severity,
            "category": category,
            "priority": priority,
            "count": max(int(count or 0), 0),
            "action": action,
            "actionType": action_type,
            "action_type": action_type,
            "suggestedAction": suggested_action,
            "suggested_action": suggested_action,
            "targetHealth": health,
            "target_health": health,
        }

    def _build_dashboard_maintenance_summary(
        self, items: list[dict[str, Any]]
    ) -> dict[str, Any]:
        severity_order = {"danger": 3, "warning": 2, "neutral": 1, "success": 0}
        strongest_severity = max(
            (item["severity"] for item in items),
            key=lambda severity: severity_order.get(severity, 0),
            default="success",
        )
        actionable_items = [item for item in items if item["severity"] != "success"]
        file_queue_count = sum(
            item["count"]
            for item in actionable_items
            if item.get("actionType") == "file_queue"
        )
        settings_count = sum(
            item["count"]
            for item in actionable_items
            if item.get("actionType") == "settings"
        )
        return {
            "total": len(items),
            "actionableCount": len(actionable_items),
            "actionable_count": len(actionable_items),
            "dangerCount": sum(1 for item in items if item["severity"] == "danger"),
            "danger_count": sum(1 for item in items if item["severity"] == "danger"),
            "warningCount": sum(1 for item in items if item["severity"] == "warning"),
            "warning_count": sum(1 for item in items if item["severity"] == "warning"),
            "successCount": sum(1 for item in items if item["severity"] == "success"),
            "success_count": sum(1 for item in items if item["severity"] == "success"),
            "neutralCount": sum(1 for item in items if item["severity"] == "neutral"),
            "neutral_count": sum(1 for item in items if item["severity"] == "neutral"),
            "fileQueueCount": file_queue_count,
            "file_queue_count": file_queue_count,
            "settingsCount": settings_count,
            "settings_count": settings_count,
            "strongestSeverity": strongest_severity,
            "strongest_severity": strongest_severity,
        }

    def _build_dashboard_operational_insight(
        self,
        key: str,
        severity: str,
        priority: int,
        count: int,
        action_type: str,
        health: Optional[str] = None,
    ) -> dict[str, Any]:
        action = {
            "type": action_type,
            "actionType": action_type,
            "action_type": action_type,
        }
        if health:
            action.update(
                {
                    "health": health,
                    "targetHealth": health,
                    "target_health": health,
                }
            )

        return {
            "key": key,
            "severity": severity,
            "priority": priority,
            "count": max(int(count or 0), 0),
            "action": action,
            "actionType": action_type,
            "action_type": action_type,
            "targetHealth": health,
            "target_health": health,
        }

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
                "statusInsights": status_insights,
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
        metadata = await self.get_file_metadata(file_id)
        detail.update(
            {
                "metadata": metadata,
                "meta": metadata,
                "note": metadata["note"],
                "tags": metadata["tags"],
                "metadataUpdatedAt": metadata["updatedAt"],
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

        updated_at = metadata.get("updatedAt") or metadata.get("updated_at")
        return {
            "note": self._normalize_metadata_note(metadata.get("note")),
            "tags": self._normalize_metadata_tags(metadata.get("tags")),
            "updatedAt": updated_at,
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
        target_type_options = self._build_admin_activity_options(activities, "targetType")
        return {
            "activities": visible_activities,
            "items": visible_activities,
            "total": len(filtered_activities),
            "storedTotal": len(activities),
            "stored_total": len(activities),
            "limit": limit,
            "filters": {
                "action": normalized_action,
                "targetType": normalized_target_type,
                "target_type": normalized_target_type,
                "keyword": normalized_keyword,
            },
            "actionOptions": action_options,
            "action_options": action_options,
            "targetTypeOptions": target_type_options,
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
                    "targetType": target_type,
                    "target_type": target_type,
                    "targetId": target_id,
                    "target_id": target_id,
                    "targetName": target_name,
                    "target_name": target_name,
                    "count": count,
                    "meta": meta or {},
                    "createdAt": created_at,
                    "created_at": created_at,
                }
            )
            if not activity:
                return None

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

        activities.sort(key=lambda item: item.get("createdAt") or "", reverse=True)
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
            activity.get("targetType") or activity.get("target_type") or "system"
        )
        if not action:
            return None

        target_name = self._normalize_admin_activity_text(
            activity.get("targetName") or activity.get("target_name")
        )
        created_at = activity.get("createdAt") or activity.get("created_at")
        if isinstance(created_at, datetime):
            created_at = created_at.isoformat()
        created_at = str(created_at or "")
        if not created_at:
            return None

        target_id = activity.get("targetId")
        if target_id is None:
            target_id = activity.get("target_id")

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
            "targetType": target_type,
            "target_type": target_type,
            "targetId": target_id,
            "target_id": target_id,
            "targetName": target_name,
            "target_name": target_name,
            "count": count,
            "meta": meta,
            "createdAt": created_at,
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
            if target_type and str(activity.get("targetType") or "").lower() != target_type:
                continue
            if keyword and not self._activity_matches_keyword(activity, keyword):
                continue
            filtered_activities.append(activity)
        return filtered_activities

    def _activity_matches_keyword(self, activity: dict[str, Any], keyword: str) -> bool:
        searchable_values = [
            activity.get("action"),
            activity.get("targetType"),
            activity.get("target_type"),
            activity.get("targetId"),
            activity.get("target_id"),
            activity.get("targetName"),
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
        created_at = preset.get("createdAt") or preset.get("created_at")
        updated_at = preset.get("updatedAt") or preset.get("updated_at")

        return {
            "id": preset_id,
            "name": name,
            "filters": normalized_filters,
            "params": normalized_filters,
            "createdAt": created_at,
            "created_at": created_at,
            "updatedAt": updated_at,
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
            "sortBy": sort_by,
            "sortOrder": sort_order,
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
        if not self._match_admin_file_health(item, health):
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

    def _match_admin_file_health(self, item: dict[str, Any], health: str) -> bool:
        if not health or health == "all":
            return True

        status_insights = item.get("statusInsights") or {}
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
            return state == "expired" or item.get("isExpired") is True
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

    def get_config(self, include_diagnostics: bool = True):
        config = dict(settings.items())
        if not include_diagnostics:
            return config

        diagnostics = self.build_config_diagnostics(config)
        return {
            **config,
            "diagnostics": diagnostics,
            "diagnosticItems": diagnostics["items"],
            "diagnostic_items": diagnostics["items"],
            "diagnosticSummary": diagnostics["summary"],
            "diagnostic_summary": diagnostics["summary"],
        }

    def build_config_diagnostics(self, config: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        config = config or dict(settings.items())
        items: list[dict[str, Any]] = []

        def add_item(
            key: str,
            severity: str,
            category: str,
            field: Optional[str],
            priority: int,
            count: int = 1,
            fields: Optional[list[str]] = None,
        ) -> None:
            target_fields = fields or ([field] if field else [])
            action = {
                "type": "field" if field else "section",
                "field": field,
                "fields": target_fields,
                "category": category,
            }
            items.append(
                {
                    "key": key,
                    "severity": severity,
                    "category": category,
                    "priority": priority,
                    "count": max(int(count or 0), 0),
                    "field": field,
                    "fields": target_fields,
                    "action": action,
                    "actionType": action["type"],
                    "action_type": action["type"],
                    "targetField": field,
                    "target_field": field,
                }
            )

        admin_token = str(config.get("admin_token") or "")
        if admin_token == settings.default_config.get("admin_token"):
            add_item("default_admin_password", "danger", "security", "admin_token", 100)

        file_storage = str(config.get("file_storage") or "local").strip().lower()
        if file_storage == "s3":
            missing_fields = [
                field
                for field in ["s3_access_key_id", "s3_secret_access_key", "s3_bucket_name"]
                if not str(config.get(field) or "").strip()
            ]
            if missing_fields:
                add_item(
                    "s3_incomplete",
                    "danger",
                    "storage",
                    missing_fields[0],
                    95,
                    count=len(missing_fields),
                    fields=missing_fields,
                )
        elif file_storage == "webdav":
            missing_fields = [
                field
                for field in ["webdav_url", "webdav_username", "webdav_password"]
                if not str(config.get(field) or "").strip()
            ]
            if missing_fields:
                add_item(
                    "webdav_incomplete",
                    "danger",
                    "storage",
                    missing_fields[0],
                    95,
                    count=len(missing_fields),
                    fields=missing_fields,
                )

        if self._to_int(config.get("openUpload")) and self._to_int(config.get("max_save_seconds")) <= 0:
            add_item("guest_upload_retention", "warning", "retention", "max_save_seconds", 80)

        if (
            self._to_int(config.get("uploadSize")) >= 50 * 1024 * 1024
            and not self._to_int(config.get("enableChunk"))
        ):
            add_item("chunking_recommended", "warning", "upload", "enableChunk", 70)

        if self._to_int(config.get("uploadMinute")) <= 0 or self._to_int(config.get("uploadCount")) <= 0:
            add_item(
                "upload_guard_disabled",
                "warning",
                "upload",
                "uploadMinute",
                60,
                fields=["uploadMinute", "uploadCount"],
            )

        if self._to_int(config.get("errorMinute")) <= 0 or self._to_int(config.get("errorCount")) <= 0:
            add_item(
                "access_guard_disabled",
                "warning",
                "security",
                "errorMinute",
                55,
                fields=["errorMinute", "errorCount"],
            )

        expire_style = config.get("expireStyle")
        if not isinstance(expire_style, list) or len(expire_style) == 0:
            add_item("expiration_style_empty", "danger", "retention", "expireStyle", 75)

        if not items:
            add_item("healthy", "success", "system", None, 10, count=0)

        items.sort(key=lambda item: (-item["priority"], item["key"]))
        summary = self._build_config_diagnostic_summary(items)
        return {
            "items": items,
            "diagnosticItems": items,
            "diagnostic_items": items,
            "summary": summary,
            "diagnosticSummary": summary,
            "diagnostic_summary": summary,
        }

    def _build_config_diagnostic_summary(self, items: list[dict[str, Any]]) -> dict[str, Any]:
        severity_order = {"danger": 3, "warning": 2, "neutral": 1, "success": 0}
        strongest_severity = max(
            (item["severity"] for item in items),
            key=lambda severity: severity_order.get(severity, 0),
            default="success",
        )
        return {
            "total": len(items),
            "dangerCount": sum(1 for item in items if item["severity"] == "danger"),
            "danger_count": sum(1 for item in items if item["severity"] == "danger"),
            "warningCount": sum(1 for item in items if item["severity"] == "warning"),
            "warning_count": sum(1 for item in items if item["severity"] == "warning"),
            "successCount": sum(1 for item in items if item["severity"] == "success"),
            "success_count": sum(1 for item in items if item["severity"] == "success"),
            "neutralCount": sum(1 for item in items if item["severity"] == "neutral"),
            "neutral_count": sum(1 for item in items if item["severity"] == "neutral"),
            "strongestSeverity": strongest_severity,
            "strongest_severity": strongest_severity,
        }

    def _to_int(self, value: Any) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

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
