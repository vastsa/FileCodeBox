# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio
import html
import time
from contextlib import asynccontextmanager
from urllib.parse import parse_qs

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from apps.admin.views import admin_api
from apps.base.models import KeyValue
from apps.base.utils import ip_limit
from apps.base.views import share_api, chunk_api, presign_api
from core.config import (
    ensure_security_settings,
    ensure_settings_row,
    initialize_system,
    is_runtime_initialized,
    refresh_settings,
)
from core.database import db_startup_lock, get_db_config, init_db
from core.logger import logger
from core.response import APIResponse
from core.settings import settings, BASE_DIR, DEFAULT_CONFIG
from core.tasks import (
    clean_expired_presign_sessions,
    clean_incomplete_uploads,
    delete_expire_files,
)
from core.version import APP_VERSION


def normalize_public_flag(value) -> int:
    if isinstance(value, str):
        return int(value.strip().lower() in {"1", "true", "on", "yes"})
    return int(bool(value))


def build_public_config() -> dict:
    return {
        "name": settings.name,
        "description": settings.description,
        "explain": settings.page_explain,
        "uploadSize": settings.uploadSize,
        "allowedFileTypes": settings.allowed_file_types,
        "expireStyle": settings.expireStyle,
        "enableChunk": settings.enableChunk,
        "openUpload": settings.openUpload,
        "notify_title": settings.notify_title,
        "notify_content": settings.notify_content,
        "show_admin_address": normalize_public_flag(settings.showAdminAddr),
        "max_save_seconds": settings.max_save_seconds,
    }


def build_public_meta() -> dict:
    return {
        "version": APP_VERSION,
        "api": {
            "legacyConfig": "/",
            "publicConfig": "/api/v1/config",
            "health": "/health",
        },
        "features": {
            "chunkUpload": bool(settings.enableChunk),
            "guestUpload": bool(settings.openUpload),
            "adminAddressVisible": bool(normalize_public_flag(settings.showAdminAddr)),
            "expirationModes": settings.expireStyle,
        },
        "limits": {
            "uploadSize": settings.uploadSize,
            "allowedFileTypes": settings.allowed_file_types,
            "maxSaveSeconds": settings.max_save_seconds,
            "uploadWindowMinutes": settings.uploadMinute,
            "uploadWindowCount": settings.uploadCount,
        },
    }


FILE_SIZE_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
SAVE_TIME_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
EXPIRE_STYLE_OPTIONS = [
    ("day", "按天"),
    ("hour", "按小时"),
    ("minute", "按分钟"),
    ("forever", "永久"),
    ("count", "按取件次数"),
]


def get_form_value(data: dict, key: str, default: str = "") -> str:
    value = data.get(key, default)
    if isinstance(value, list):
        value = value[-1] if value else default
    return str(value if value is not None else default)


def get_form_list(data: dict, key: str) -> list[str]:
    value = data.get(key, [])
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if value:
        return [str(value)]
    return []


def normalize_bool_field(data: dict, key: str, default: bool) -> bool:
    if key not in data:
        return default
    return get_form_value(data, key).lower() in {"1", "true", "on", "yes"}


def parse_int_field(
    data: dict,
    key: str,
    default: int,
    label: str,
    min_value: int = 0,
    max_value: int | None = None,
) -> int:
    raw_value = get_form_value(data, key, str(default)).strip()
    try:
        value = int(raw_value)
    except ValueError:
        raise ValueError(f"{label} 必须是整数")
    if value < min_value:
        raise ValueError(f"{label} 不能小于 {min_value}")
    if max_value is not None and value > max_value:
        raise ValueError(f"{label} 不能大于 {max_value}")
    return value


def parse_allowed_file_types(value: str) -> list[str]:
    items = [item.strip() for item in value.split(",") if item.strip()]
    return items or ["*"]


def parse_setup_options(data: dict) -> dict:
    upload_size_unit = get_form_value(data, "upload_size_unit", "MB").upper()
    if upload_size_unit not in FILE_SIZE_UNITS:
        raise ValueError("文件大小单位不正确")
    upload_size_value = parse_int_field(
        data, "upload_size_value", 10, "文件大小限制", min_value=1
    )

    save_time_unit = get_form_value(data, "save_time_unit", "day")
    if save_time_unit not in SAVE_TIME_UNITS:
        raise ValueError("最长保存时间单位不正确")
    save_time_value = parse_int_field(
        data, "save_time_value", 0, "最长保存时间", min_value=0
    )

    expire_styles = get_form_list(data, "expireStyle")
    valid_expire_styles = {style for style, _label in EXPIRE_STYLE_OPTIONS}
    expire_styles = [style for style in expire_styles if style in valid_expire_styles]
    if not expire_styles:
        raise ValueError("至少需要选择一种过期方式")

    code_generate_type = get_form_value(
        data, "code_generate_type", DEFAULT_CONFIG["code_generate_type"]
    )
    if code_generate_type not in {"number", "secret"}:
        raise ValueError("提取码类型不正确")

    return {
        "allowed_file_types": parse_allowed_file_types(
            get_form_value(data, "allowed_file_types", "*")
        ),
        "code_generate_type": code_generate_type,
        "enableChunk": int(normalize_bool_field(data, "enableChunk", False)),
        "errorCount": parse_int_field(
            data, "errorCount", DEFAULT_CONFIG["errorCount"], "取件错误次数限制", 1
        ),
        "errorMinute": parse_int_field(
            data, "errorMinute", DEFAULT_CONFIG["errorMinute"], "取件错误检测窗口", 1
        ),
        "expireStyle": expire_styles,
        "max_save_seconds": save_time_value * SAVE_TIME_UNITS[save_time_unit],
        "openUpload": int(normalize_bool_field(data, "openUpload", True)),
        "uploadCount": parse_int_field(
            data, "uploadCount", DEFAULT_CONFIG["uploadCount"], "上传次数限制", 1
        ),
        "uploadMinute": parse_int_field(
            data, "uploadMinute", DEFAULT_CONFIG["uploadMinute"], "上传检测窗口", 1
        ),
        "uploadSize": upload_size_value * FILE_SIZE_UNITS[upload_size_unit],
    }


def build_expire_style_inputs(selected_styles: list[str]) -> str:
    inputs = []
    selected = set(selected_styles)
    for style, label in EXPIRE_STYLE_OPTIONS:
        checked = " checked" if style in selected else ""
        inputs.append(
            f'<label class="check"><input type="checkbox" name="expireStyle" value="{style}"{checked}> {label}</label>'
        )
    return "\n        ".join(inputs)


def build_setup_page(error: str = "", form: dict | None = None) -> str:
    form = form or {}
    escaped_error = html.escape(error)
    escaped_site_name = html.escape(
        get_form_value(form, "site_name", DEFAULT_CONFIG["name"])
    )
    escaped_allowed_types = html.escape(get_form_value(form, "allowed_file_types", "*"))
    upload_size_value = html.escape(get_form_value(form, "upload_size_value", "10"))
    upload_size_unit = get_form_value(form, "upload_size_unit", "MB").upper()
    save_time_value = html.escape(get_form_value(form, "save_time_value", "0"))
    save_time_unit = get_form_value(form, "save_time_unit", "day")
    upload_minute = html.escape(
        get_form_value(form, "uploadMinute", str(DEFAULT_CONFIG["uploadMinute"]))
    )
    upload_count = html.escape(
        get_form_value(form, "uploadCount", str(DEFAULT_CONFIG["uploadCount"]))
    )
    error_minute = html.escape(
        get_form_value(form, "errorMinute", str(DEFAULT_CONFIG["errorMinute"]))
    )
    error_count = html.escape(
        get_form_value(form, "errorCount", str(DEFAULT_CONFIG["errorCount"]))
    )
    open_upload_checked = (
        " checked" if normalize_bool_field(form, "openUpload", True) else ""
    )
    chunk_checked = (
        " checked" if normalize_bool_field(form, "enableChunk", False) else ""
    )
    code_generate_type = get_form_value(
        form, "code_generate_type", DEFAULT_CONFIG["code_generate_type"]
    )
    selected_expire_styles = get_form_list(form, "expireStyle") or list(
        DEFAULT_CONFIG["expireStyle"]
    )
    expire_style_inputs = build_expire_style_inputs(selected_expire_styles)
    size_unit_options = "\n".join(
        f'<option value="{unit}"{" selected" if unit == upload_size_unit else ""}>{unit}</option>'
        for unit in FILE_SIZE_UNITS
    )
    save_time_unit_options = "\n".join(
        f'<option value="{unit}"{" selected" if unit == save_time_unit else ""}>{label}</option>'
        for unit, label in [
            ("second", "秒"),
            ("minute", "分钟"),
            ("hour", "小时"),
            ("day", "天"),
        ]
    )
    code_type_options = "\n".join(
        f'<option value="{value}"{" selected" if value == code_generate_type else ""}>{label}</option>'
        for value, label in [("number", "数字"), ("secret", "随机字符")]
    )
    error_block = (
        f'<div class="alert" role="alert">{escaped_error}</div>' if escaped_error else ""
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>初始化 FileCodeBox</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f5f5f7;
      --panel: rgba(255, 255, 255, .86);
      --panel-strong: rgba(255, 255, 255, .96);
      --text: #18181b;
      --muted: #71717a;
      --line: rgba(228, 228, 231, .9);
      --line-strong: rgba(212, 212, 216, .95);
      --primary: #18181b;
      --primary-soft: #f4f4f5;
      --danger-bg: #fef2f2;
      --danger: #b91c1c;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 14px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: var(--bg);
      color: var(--text);
    }}
    main {{
      width: min(100%, 1040px);
      padding: 14px;
      border: 1px solid rgba(255, 255, 255, .8);
      border-radius: 20px;
      background: rgba(255, 255, 255, .62);
      box-shadow: 0 22px 70px -34px rgba(24, 24, 27, .32);
      backdrop-filter: blur(22px);
    }}
    .setup-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 10px 10px 12px;
    }}
    .brand-mark {{
      flex: 0 0 auto;
      width: 40px;
      height: 40px;
      display: grid;
      place-items: center;
      border-radius: 14px;
      background: #18181b;
      color: #fff;
      font-weight: 800;
      letter-spacing: 0;
      box-shadow: 0 16px 34px -14px rgba(24, 24, 27, .42);
    }}
    .title-wrap {{
      min-width: 0;
      display: flex;
      align-items: center;
      gap: 12px;
    }}
    h1 {{
      margin: 0;
      font-size: 21px;
      line-height: 1.25;
      letter-spacing: 0;
      font-weight: 750;
    }}
    p {{
      margin: 2px 0 0;
      color: var(--muted);
      line-height: 1.35;
      font-size: 13px;
    }}
    form {{
      margin: 0;
      padding: 12px;
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--panel);
    }}
    .panel-grid {{
      display: grid;
      grid-template-columns: 1.05fr 1fr 1fr;
      gap: 10px;
    }}
    .panel {{
      min-width: 0;
      padding: 10px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: rgba(255, 255, 255, .68);
    }}
    .panel-wide {{
      grid-column: 1 / -1;
      display: grid;
      grid-template-columns: minmax(0, 1.3fr) minmax(0, .9fr);
      gap: 12px;
      align-items: end;
    }}
    .panel-title {{
      margin: 0 0 2px;
      color: #18181b;
      font-size: 13px;
      font-weight: 760;
    }}
    label {{
      display: block;
      margin: 8px 0 5px;
      font-weight: 650;
      font-size: 12px;
      color: #3f3f46;
    }}
    input, select {{
      width: 100%;
      height: 34px;
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 0 10px;
      font: inherit;
      color: var(--text);
      outline: none;
      background: rgba(255, 255, 255, .84);
      transition: border-color .2s ease, box-shadow .2s ease, background-color .2s ease;
    }}
    input:focus, select:focus {{
      border-color: #a1a1aa;
      background: #fff;
      box-shadow: 0 10px 22px -12px rgba(24, 24, 27, .2), 0 0 0 3px rgba(24, 24, 27, .06);
    }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 6px 12px;
    }}
    .full {{ grid-column: 1 / -1; }}
    .span-2 {{ grid-column: span 2; }}
    .row {{
      display: grid;
      grid-template-columns: minmax(0, 1fr) 88px;
      gap: 8px;
    }}
    .checks {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 5px;
    }}
    .check {{
      display: flex;
      align-items: center;
      gap: 8px;
      min-height: 36px;
      margin: 0;
      padding: 0 9px;
      border: 1px solid var(--line);
      border-radius: 10px;
      font-weight: 550;
      font-size: 13px;
      color: var(--text);
      white-space: nowrap;
      background: rgba(255, 255, 255, .72);
      transition: border-color .2s ease, background-color .2s ease, box-shadow .2s ease;
    }}
    .check:hover {{
      border-color: var(--line-strong);
      background: #fff;
      box-shadow: 0 8px 20px -8px rgba(0, 0, 0, .1);
    }}
    .check input {{
      width: 16px;
      height: 16px;
      padding: 0;
      box-shadow: none;
    }}
    .section-title {{
      display: none;
    }}
    .help {{
      margin: 4px 0 0;
      font-size: 12px;
      color: var(--muted);
    }}
    .alert {{
      margin-bottom: 8px;
      padding: 9px 12px;
      border-radius: 12px;
      background: var(--danger-bg);
      color: var(--danger);
      font-size: 13px;
    }}
    button {{
      width: 100%;
      height: 38px;
      margin-top: 12px;
      border: 0;
      border-radius: 12px;
      background: var(--primary);
      color: white;
      font: inherit;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 16px 34px -14px rgba(24, 24, 27, .42);
      transition: background-color .2s ease, box-shadow .2s ease;
    }}
    button:hover {{
      background: #27272a;
      box-shadow: 0 16px 34px -14px rgba(24, 24, 27, .56);
    }}
    .hint {{
      margin-top: 8px;
      margin-bottom: 0;
      font-size: 12px;
    }}
    .compact-help {{
      display: inline;
      margin-left: 6px;
      color: var(--muted);
      font-weight: 500;
      font-size: 12px;
    }}
    .topline {{
      display: none;
    }}
    .badge {{
      min-height: 26px;
      display: inline-flex;
      align-items: center;
      padding: 0 10px;
      border: 1px solid var(--line);
      border-radius: 999px;
      background: rgba(255, 255, 255, .76);
      color: #52525b;
      font-size: 12px;
      font-weight: 650;
      white-space: nowrap;
    }}
    @media (max-width: 640px) {{
      body {{ padding: 10px; }}
      main {{ padding: 10px; }}
      .setup-header {{ align-items: flex-start; padding: 6px 4px 10px; }}
      .title-wrap {{ align-items: flex-start; }}
      .panel-grid, .panel-wide {{ grid-template-columns: 1fr; }}
      .grid, .checks {{ grid-template-columns: 1fr; }}
      .span-2 {{ grid-column: auto; }}
      .row {{ grid-template-columns: 1fr; }}
      .badge {{ display: none; }}
    }}
  </style>
</head>
<body>
  <main>
    <div class="setup-header">
      <div class="title-wrap">
        <div class="brand-mark">FCB</div>
        <div>
          <h1>初始化 FileCodeBox</h1>
          <p>首次配置管理员密码、上传限制和取件策略，后续可在后台调整。</p>
        </div>
      </div>
      <span class="badge">首次配置向导</span>
    </div>
    <form method="post" action="/setup" autocomplete="off">
      {error_block}
      <div class="panel-grid">
        <section class="panel">
          <div class="panel-title">基础设置</div>
          <label for="site_name">站点名称</label>
          <input id="site_name" name="site_name" maxlength="80" value="{escaped_site_name}" placeholder="文件快递柜 - FileCodeBox">

          <label for="admin_password">管理员密码</label>
          <input id="admin_password" name="admin_password" type="password" minlength="8" required autofocus>

          <label for="confirm_password">确认管理员密码</label>
          <input id="confirm_password" name="confirm_password" type="password" minlength="8" required>
        </section>

        <section class="panel">
          <div class="panel-title">上传设置</div>
          <label for="upload_size_value">单文件大小限制</label>
          <div class="row">
            <input id="upload_size_value" name="upload_size_value" type="number" min="1" value="{upload_size_value}" required>
            <select name="upload_size_unit" aria-label="文件大小单位">
              {size_unit_options}
            </select>
          </div>

          <label for="uploadCount">上传频率 <span class="compact-help">次数 / 分钟</span></label>
          <div class="row">
            <input id="uploadCount" name="uploadCount" type="number" min="1" value="{upload_count}" required>
            <input name="uploadMinute" type="number" min="1" value="{upload_minute}" aria-label="上传检测窗口分钟" required>
          </div>

          <div class="grid">
            <input type="hidden" name="openUpload" value="0">
            <label class="check"><input type="checkbox" name="openUpload" value="1"{open_upload_checked}> 允许游客上传</label>
            <input type="hidden" name="enableChunk" value="0">
            <label class="check"><input type="checkbox" name="enableChunk" value="1"{chunk_checked}> 启用切片上传</label>
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">取件与保存</div>
          <label for="errorCount">取件错误频率 <span class="compact-help">次数 / 分钟</span></label>
          <div class="row">
            <input id="errorCount" name="errorCount" type="number" min="1" value="{error_count}" required>
            <input name="errorMinute" type="number" min="1" value="{error_minute}" aria-label="取件错误检测窗口分钟" required>
          </div>

          <label for="save_time_value">最长保存时间</label>
          <div class="row">
            <input id="save_time_value" name="save_time_value" type="number" min="0" value="{save_time_value}" required>
            <select name="save_time_unit" aria-label="最长保存时间单位">
              {save_time_unit_options}
            </select>
          </div>

          <label for="code_generate_type">提取码类型</label>
          <select id="code_generate_type" name="code_generate_type">
            {code_type_options}
          </select>
        </section>

        <section class="panel panel-wide">
          <div>
            <div class="panel-title">可用策略</div>
          <label>允许的过期方式</label>
          <div class="checks">
            {expire_style_inputs}
          </div>
          </div>

          <div>
          <label for="allowed_file_types">允许文件类型 <span class="compact-help">逗号分隔，* 表示不限制</span></label>
          <input id="allowed_file_types" name="allowed_file_types" value="{escaped_allowed_types}" placeholder="* 或 .zip, image/*">
          </div>
        </section>
      </div>
      <button type="submit">完成初始化</button>
    </form>
  </main>
</body>
</html>"""


def build_setup_success_page() -> str:
    return """<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="2;url=/#/admin">
  <title>初始化完成</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      padding: 24px;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: #f6f8fb;
      color: #172033;
    }
    main {
      width: min(100%, 420px);
      padding: 28px;
      border: 1px solid #d9e1ec;
      border-radius: 8px;
      background: #fff;
      text-align: center;
      box-shadow: 0 18px 50px rgba(23, 32, 51, .08);
    }
    h1 { margin: 0 0 10px; font-size: 24px; letter-spacing: 0; }
    p { margin: 0 0 22px; color: #60708a; line-height: 1.65; }
    a {
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-height: 42px;
      padding: 0 18px;
      border-radius: 6px;
      background: #2563eb;
      color: white;
      text-decoration: none;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <main>
    <h1>初始化完成</h1>
    <p>管理员密码已设置，请使用刚才的密码登录后台。</p>
    <a href="/#/admin">进入后台</a>
  </main>
</body>
</html>"""


def setup_response(content: str, status_code: int = 200) -> HTMLResponse:
    return HTMLResponse(
        content=content,
        status_code=status_code,
        media_type="text/html",
        headers={"Cache-Control": "no-store"},
    )


def is_setup_path(path: str) -> bool:
    return path.rstrip("/") == "/setup"


def wants_html_response(request: Request) -> bool:
    if request.method not in {"GET", "HEAD"}:
        return False
    accept = request.headers.get("accept", "")
    return not accept or "text/html" in accept or "*/*" in accept


async def read_setup_payload(request: Request) -> dict:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        data = await request.json()
        return data if isinstance(data, dict) else {}

    body = (await request.body()).decode("utf-8")
    return {
        key: values if len(values) > 1 else values[-1]
        for key, values in parse_qs(body).items()
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化应用...")
    # 初始化数据库
    await init_db()

    # 加载配置（多进程下串行化启动写操作）
    async with db_startup_lock():
        await load_config()
    # 启动后台任务
    task = asyncio.create_task(delete_expire_files())
    chunk_cleanup_task = asyncio.create_task(clean_incomplete_uploads())
    presign_cleanup_task = asyncio.create_task(clean_expired_presign_sessions())
    logger.info("应用初始化完成")

    try:
        yield
    finally:
        # 清理操作
        logger.info("正在关闭应用...")
        task.cancel()
        chunk_cleanup_task.cancel()
        presign_cleanup_task.cancel()
        await asyncio.gather(
            task,
            chunk_cleanup_task,
            presign_cleanup_task,
            return_exceptions=True,
        )
        await Tortoise.close_connections()
        logger.info("应用已关闭")


async def load_config():
    await ensure_settings_row()
    await KeyValue.update_or_create(
        key="sys_start", defaults={"value": int(time.time() * 1000)}
    )
    await refresh_settings()
    await ensure_security_settings()

    ip_limit["error"].minutes = settings.errorMinute
    ip_limit["error"].count = settings.errorCount
    ip_limit["upload"].minutes = settings.uploadMinute
    ip_limit["upload"].count = settings.uploadCount

app = FastAPI(lifespan=lifespan, version=APP_VERSION)

@app.middleware("http")
async def refresh_settings_middleware(request, call_next):
    await refresh_settings()
    if not is_runtime_initialized() and not is_setup_path(request.url.path):
        if wants_html_response(request):
            return setup_response(build_setup_page())
        return JSONResponse(
            status_code=428,
            content={
                "code": 428,
                "message": "系统未初始化，请先完成初始化",
                "msg": "系统未初始化，请先完成初始化",
                "detail": {"setup": "/setup"},
            },
        )
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 使用 register_tortoise 来添加异常处理器
register_tortoise(
    app,
    config=get_db_config(),
    generate_schemas=False,
    add_exception_handlers=True,
)

app.include_router(share_api)
app.include_router(chunk_api)
app.include_router(presign_api)
app.include_router(presign_api, prefix="/api")
app.include_router(admin_api)


@app.get("/setup", include_in_schema=False)
@app.get("/setup/", include_in_schema=False)
async def setup_page():
    if is_runtime_initialized():
        return RedirectResponse(url="/", status_code=303)
    return setup_response(build_setup_page())


@app.post("/setup", include_in_schema=False)
@app.post("/setup/", include_in_schema=False)
async def setup_submit(request: Request):
    if is_runtime_initialized():
        return RedirectResponse(url="/", status_code=303)

    data = await read_setup_payload(request)
    admin_password = str(data.get("admin_password") or "")
    confirm_password = str(data.get("confirm_password") or "")
    site_name = str(data.get("site_name") or "")

    if admin_password != confirm_password:
        return setup_response(build_setup_page("两次输入的管理员密码不一致", data), 400)

    try:
        setup_options = parse_setup_options(data)
        await initialize_system(
            admin_password=admin_password,
            site_name=site_name,
            setup_options=setup_options,
        )
    except ValueError as exc:
        return setup_response(build_setup_page(str(exc), data), 400)

    if "application/json" in request.headers.get("accept", ""):
        return APIResponse(detail={"ok": True, "admin": "/#/admin"})
    return setup_response(build_setup_success_page())


def resolve_theme_root():
    themes_root = (BASE_DIR / "themes").resolve()
    theme_root = (BASE_DIR / str(settings.themesSelect)).resolve()
    try:
        theme_root.relative_to(themes_root)
    except ValueError:
        theme_root = (BASE_DIR / DEFAULT_CONFIG["themesSelect"]).resolve()
    if not theme_root.exists():
        theme_root = (BASE_DIR / DEFAULT_CONFIG["themesSelect"]).resolve()
    return theme_root


def resolve_theme_file(*parts: str):
    theme_root = resolve_theme_root()
    file_path = theme_root.joinpath(*parts).resolve()
    # 防止通过 /assets/../ 读取主题目录外的文件。
    try:
        file_path.relative_to(theme_root)
    except ValueError:
        raise HTTPException(status_code=404, detail="资源不存在")
    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="资源不存在")
    return file_path


@app.get("/assets/{asset_path:path}", include_in_schema=False)
async def theme_asset(asset_path: str):
    return FileResponse(resolve_theme_file("assets", asset_path))


@app.exception_handler(404)
@app.get("/")
async def index(request=None, exc=None):
    return HTMLResponse(
        content=resolve_theme_file("index.html")
        .read_text(encoding="utf-8")
        .replace("{{title}}", str(settings.name))
        .replace("{{description}}", str(settings.description))
        .replace("{{keywords}}", str(settings.keywords))
        .replace("{{opacity}}", str(settings.opacity))
        .replace("{{background}}", str(settings.background)),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/robots.txt")
async def robots():
    return HTMLResponse(content=settings.robotsText, media_type="text/plain")


@app.post("/")
async def get_config():
    return APIResponse(detail=build_public_config())


@app.get("/api/v1/config")
async def get_public_config():
    return APIResponse(
        detail={
            "config": build_public_config(),
            "meta": build_public_meta(),
        }
    )


@app.get("/health")
async def health_check():
    return APIResponse(
        detail={
            "status": "ok",
            "version": APP_VERSION,
            "storage": settings.file_storage,
            "theme": settings.themesSelect,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="main:app",
        host=settings.serverHost,
        port=settings.serverPort,
        reload=False,
        workers=settings.serverWorkers,
    )
