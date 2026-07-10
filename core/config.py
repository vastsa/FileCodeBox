from apps.base.models import KeyValue
from apps.base.utils import ip_limit
from core.database import db_startup_lock
from core.logger import logger
from core.security import (
    generate_jwt_secret,
    is_config_initialized,
    is_valid_jwt_secret,
    prepare_security_config,
)
from core.settings import DEFAULT_CONFIG, settings
from core.utils import hash_password


MIN_ADMIN_PASSWORD_LENGTH = 8
SETUP_CONFIG_FIELDS = {
    "allowed_file_types",
    "code_generate_type",
    "enableChunk",
    "errorCount",
    "errorMinute",
    "expireStyle",
    "max_save_seconds",
    "name",
    "openUpload",
    "uploadCount",
    "uploadMinute",
    "uploadSize",
}


async def ensure_settings_row() -> None:
    initial_security = prepare_security_config(DEFAULT_CONFIG)
    _, created = await KeyValue.get_or_create(
        key="settings", defaults={"value": initial_security.config}
    )
    if created:
        logger.warning(
            "系统尚未初始化，请在浏览器中打开站点并完成管理员密码设置"
        )


async def ensure_security_settings() -> None:
    config_record = await KeyValue.filter(key="settings").first()
    if not config_record:
        return

    current_config = {**DEFAULT_CONFIG, **(config_record.value or {})}
    security_config = prepare_security_config(current_config)
    if not security_config.changed:
        return

    config_record.value = security_config.config
    await config_record.save()
    if security_config.setup_required:
        logger.warning("检测到空密码或旧版默认管理员密码，请通过初始化页面重新设置")
    elif security_config.password_hashed:
        logger.info("已将管理员密码迁移为哈希存储")
    if security_config.jwt_secret_rotated:
        logger.info("已生成独立 JWT 签名密钥")
    await refresh_settings()


def _sync_ip_limits() -> None:
    ip_limit["error"].minutes = settings.errorMinute
    ip_limit["error"].count = settings.errorCount
    ip_limit["metadata"].minutes = settings.errorMinute
    ip_limit["metadata"].count = settings.errorCount
    ip_limit["upload"].minutes = settings.uploadMinute
    ip_limit["upload"].count = settings.uploadCount


async def refresh_settings() -> None:
    """从数据库读取最新配置并应用到运行时。"""
    config_record = await KeyValue.filter(key="settings").first()
    settings.user_config = config_record.value if config_record and config_record.value else {}
    _sync_ip_limits()


def is_runtime_initialized() -> bool:
    return is_config_initialized(dict(settings.items()))


async def initialize_system(
    admin_password: str,
    site_name: str | None = None,
    setup_options: dict | None = None,
) -> None:
    password = str(admin_password or "").strip()
    if len(password) < MIN_ADMIN_PASSWORD_LENGTH:
        raise ValueError(f"管理员密码至少需要 {MIN_ADMIN_PASSWORD_LENGTH} 位")

    async with db_startup_lock():
        config_record = await KeyValue.filter(key="settings").first()
        current_config = {
            **DEFAULT_CONFIG,
            **(config_record.value if config_record and config_record.value else {}),
        }
        if is_config_initialized(current_config):
            raise ValueError("系统已经初始化，请直接登录后台")

        next_config = dict(current_config)
        for key, value in (setup_options or {}).items():
            if key in SETUP_CONFIG_FIELDS:
                next_config[key] = value

        normalized_site_name = str(site_name or "").strip()
        if normalized_site_name:
            next_config["name"] = normalized_site_name[:80]

        next_config["admin_token"] = hash_password(password)
        if not is_valid_jwt_secret(next_config.get("jwt_secret")):
            next_config["jwt_secret"] = generate_jwt_secret()

        await KeyValue.update_or_create(key="settings", defaults={"value": next_config})
    await refresh_settings()
