import json

from tortoise import connections

# 配置键驼峰 -> snake_case 统一（2.5）。settings 存于 KeyValue 表的 JSON 值中，
# 迁移在 Python 层读取、改写键名后写回，保证存量部署升级后键名与代码一致。

KEY_RENAMES = {
    "adminSessionExpire": "admin_session_expire",
    "enableChunk": "enable_chunk",
    "errorCount": "error_count",
    "errorMinute": "error_minute",
    "expireStyle": "expire_style",
    "loginCount": "login_count",
    "loginMinute": "login_minute",
    "openUpload": "open_upload",
    "robotsText": "robots_text",
    "serverHost": "server_host",
    "serverPort": "server_port",
    "serverWorkers": "server_workers",
    "showAdminAddr": "show_admin_addr",
    "storageLimit": "storage_limit",
    "themesChoices": "themes_choices",
    "themesSelect": "themes_select",
    "trustedProxies": "trusted_proxies",
    "uploadCount": "upload_count",
    "uploadMinute": "upload_minute",
    "uploadSize": "upload_size",
}


async def migrate():
    conn = connections.get("default")
    rows = await conn.execute_query_dict(
        "SELECT id, value FROM keyvalue WHERE key = 'settings'"
    )
    for row in rows:
        value = row["value"]
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except ValueError:
                continue
        if not isinstance(value, dict):
            continue
        renamed = {KEY_RENAMES.get(k, k): v for k, v in value.items()}
        if renamed != value:
            await conn.execute_query(
                "UPDATE keyvalue SET value = ? WHERE id = ?",
                [json.dumps(renamed, ensure_ascii=False), row["id"]],
            )
