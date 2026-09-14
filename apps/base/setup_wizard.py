"""Setup wizard: form parsing rules and the two admin-facing HTML pages.

Pure presentation/logic — no router here; routes live in apps.base.pages.
"""
import html
from urllib.parse import parse_qs

from fastapi import Request
from fastapi.responses import HTMLResponse

from core.settings import DEFAULT_CONFIG, settings
from core.version import APP_VERSION


FILE_SIZE_UNITS = {"KB": 1024, "MB": 1024**2, "GB": 1024**3}
SAVE_TIME_UNITS = {"second": 1, "minute": 60, "hour": 3600, "day": 86400}
EXPIRE_STYLE_OPTIONS = [
    ("day", "按天"),
    ("hour", "按小时"),
    ("minute", "按分钟"),
    ("forever", "永久"),
    ("count", "按取件次数"),
]


def normalize_public_flag(value) -> int:
    if isinstance(value, str):
        return int(value.strip().lower() in {"1", "true", "on", "yes"})
    return int(bool(value))


def build_public_config() -> dict:
    return {
        "name": settings.name,
        "description": settings.description,
        "explain": settings.page_explain,
        "upload_size": settings.upload_size,
        "allowed_file_types": settings.allowed_file_types,
        "expire_style": settings.expire_style,
        "enable_chunk": settings.enable_chunk,
        "open_upload": settings.open_upload,
        "notify_title": settings.notify_title,
        "notify_content": settings.notify_content,
        "show_admin_address": normalize_public_flag(settings.show_admin_addr),
        "max_save_seconds": settings.max_save_seconds,
    }


def build_public_meta() -> dict:
    return {
        "version": APP_VERSION,
        "api": {
            "legacy_config": "/",
            "public_config": "/api/v1/config",
            "health": "/health",
        },
        "features": {
            "chunk_upload": bool(settings.enable_chunk),
            "guest_upload": bool(settings.open_upload),
            "admin_address_visible": bool(normalize_public_flag(settings.show_admin_addr)),
            "expiration_modes": settings.expire_style,
        },
        "limits": {
            "upload_size": settings.upload_size,
            "allowed_file_types": settings.allowed_file_types,
            "max_save_seconds": settings.max_save_seconds,
            "upload_window_minutes": settings.upload_minute,
            "upload_window_count": settings.upload_count,
        },
    }





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

    expire_styles = get_form_list(data, "expire_style")
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
        "enable_chunk": int(normalize_bool_field(data, "enable_chunk", False)),
        "error_count": parse_int_field(
            data, "error_count", DEFAULT_CONFIG["error_count"], "取件错误次数限制", 1
        ),
        "error_minute": parse_int_field(
            data, "error_minute", DEFAULT_CONFIG["error_minute"], "取件错误检测窗口", 1
        ),
        "login_count": parse_int_field(
            data, "login_count", DEFAULT_CONFIG["login_count"], "登录失败次数限制", 1
        ),
        "login_minute": parse_int_field(
            data, "login_minute", DEFAULT_CONFIG["login_minute"], "登录失败检测窗口", 1
        ),
        "expire_style": expire_styles,
        "max_save_seconds": save_time_value * SAVE_TIME_UNITS[save_time_unit],
        "open_upload": int(normalize_bool_field(data, "open_upload", True)),
        "upload_count": parse_int_field(
            data, "upload_count", DEFAULT_CONFIG["upload_count"], "上传次数限制", 1
        ),
        "upload_minute": parse_int_field(
            data, "upload_minute", DEFAULT_CONFIG["upload_minute"], "上传检测窗口", 1
        ),
        "upload_size": upload_size_value * FILE_SIZE_UNITS[upload_size_unit],
    }

def build_expire_style_inputs(selected_styles: list[str]) -> str:
    inputs = []
    selected = set(selected_styles)
    for style, label in EXPIRE_STYLE_OPTIONS:
        checked = " checked" if style in selected else ""
        inputs.append(
            f'<label class="check"><input type="checkbox" name="expire_style" value="{style}"{checked}> {label}</label>'
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
        get_form_value(form, "upload_minute", str(DEFAULT_CONFIG["upload_minute"]))
    )
    upload_count = html.escape(
        get_form_value(form, "upload_count", str(DEFAULT_CONFIG["upload_count"]))
    )
    error_minute = html.escape(
        get_form_value(form, "error_minute", str(DEFAULT_CONFIG["error_minute"]))
    )
    error_count = html.escape(
        get_form_value(form, "error_count", str(DEFAULT_CONFIG["error_count"]))
    )
    login_minute = html.escape(
        get_form_value(form, "login_minute", str(DEFAULT_CONFIG["login_minute"]))
    )
    login_count = html.escape(
        get_form_value(form, "login_count", str(DEFAULT_CONFIG["login_count"]))
    )
    open_upload_checked = (
        " checked" if normalize_bool_field(form, "open_upload", True) else ""
    )
    chunk_checked = (
        " checked" if normalize_bool_field(form, "enable_chunk", False) else ""
    )
    code_generate_type = get_form_value(
        form, "code_generate_type", DEFAULT_CONFIG["code_generate_type"]
    )
    selected_expire_styles = get_form_list(form, "expire_style") or list(
        DEFAULT_CONFIG["expire_style"]
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

          <label for="upload_count">上传频率 <span class="compact-help">次数 / 分钟</span></label>
          <div class="row">
            <input id="upload_count" name="upload_count" type="number" min="1" value="{upload_count}" required>
            <input name="upload_minute" type="number" min="1" value="{upload_minute}" aria-label="上传检测窗口分钟" required>
          </div>

          <div class="grid">
            <input type="hidden" name="open_upload" value="0">
            <label class="check"><input type="checkbox" name="open_upload" value="1"{open_upload_checked}> 允许游客上传</label>
            <input type="hidden" name="enable_chunk" value="0">
            <label class="check"><input type="checkbox" name="enable_chunk" value="1"{chunk_checked}> 启用切片上传</label>
          </div>
        </section>

        <section class="panel">
          <div class="panel-title">取件与保存</div>
          <label for="error_count">取件错误频率 <span class="compact-help">次数 / 分钟</span></label>
          <div class="row">
            <input id="error_count" name="error_count" type="number" min="1" value="{error_count}" required>
            <input name="error_minute" type="number" min="1" value="{error_minute}" aria-label="取件错误检测窗口分钟" required>
          </div>

          <label for="login_count">管理员登录失败频率 <span class="compact-help">次数 / 分钟</span></label>
          <div class="row">
            <input id="login_count" name="login_count" type="number" min="1" value="{login_count}" required>
            <input name="login_minute" type="number" min="1" value="{login_minute}" aria-label="登录失败检测窗口分钟" required>
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
