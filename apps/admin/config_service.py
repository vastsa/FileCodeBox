"""System config write path (ConfigService) + the KeyValue JSON lock.

keyvalue_write_lock lives here because ConfigService.update_config is its
primary consumer; FileService imports it (one-way, no cycle).
"""
import asyncio

from fastapi import HTTPException

from core.settings import (
    ADMIN_SESSION_EXPIRE_MAX,
    ADMIN_SESSION_EXPIRE_MIN,
    settings,
)
from apps.base.config import refresh_settings
from core.security import (
    INTERNAL_CONFIG_KEYS,
    OUTBOUND_ENDPOINT_CONFIG_KEYS,
    generate_jwt_secret,
    validate_outbound_endpoint,
    validate_outbound_hostname,
)
from apps.base.models import KeyValue
from core.utils import hash_password, is_password_hashed, validate_background_url

# KeyValue 里的 settings/activities/presets 都是整块 JSON 读-改-写；
# 进程内写锁串行化这三个写路径，避免并发管理操作互相覆盖（last-writer-wins）。
# 多进程部署下锁不跨进程——文档已锁定单 worker 部署。
keyvalue_write_lock = asyncio.Lock()


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
            session_expire = int(str(next_config.get("admin_session_expire")))
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

        # 只校验"发生变化"的值：企业内网 minio/webdav 是正当场景，存量部署历史
        # 合法写入的内网 endpoint 若每次保存都重新校验，会连无关设置都保存不了
        # （background 曾有同款回归，上游 #528 修复过——本处沿用同一语义）。
        # s3_hostname 是裸主机名（存储层按 https://{hostname} 拼接），单独分档校验。
        for endpoint_key in OUTBOUND_ENDPOINT_CONFIG_KEYS:
            if endpoint_key not in next_config:
                continue
            candidate = str(next_config[endpoint_key] or "")
            current = str(getattr(settings, endpoint_key, "") or "")
            if candidate == current:
                continue
            validator = (
                validate_outbound_hostname
                if endpoint_key == "s3_hostname"
                else validate_outbound_endpoint
            )
            try:
                # 写回规范化值（validator 去除首尾空白）：校验通过但入库脏值
                # 会让存储层在连接期才报错，应在校验点归一。
                next_config[endpoint_key] = validator(candidate)
            except ValueError as exc:
                raise HTTPException(status_code=400, detail=str(exc))

        if admin_password_changed:
            next_config["jwt_secret"] = generate_jwt_secret()

        async with keyvalue_write_lock:
            await KeyValue.update_or_create(key="settings", defaults={"value": next_config})
        await refresh_settings(force=True)

