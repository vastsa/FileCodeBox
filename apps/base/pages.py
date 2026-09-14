"""Public-facing pages and routes: setup wizard, theme assets, index,
robots.txt, and the public config endpoints."""
import html

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from apps.base.config import initialize_system, is_runtime_initialized
from apps.base.setup_wizard import (
    build_public_config,
    build_public_meta,
    build_setup_page,
    build_setup_success_page,
    parse_setup_options,
    read_setup_payload,
    setup_response,
)
from core.response import APIResponse
from core.settings import BASE_DIR, DEFAULT_CONFIG, settings
from core.version import APP_VERSION

router = APIRouter()


@router.get("/setup", include_in_schema=False)
@router.get("/setup/", include_in_schema=False)
async def setup_page():
    if is_runtime_initialized():
        return RedirectResponse(url="/", status_code=303)
    return setup_response(build_setup_page())


@router.post("/setup", include_in_schema=False)
@router.post("/setup/", include_in_schema=False)
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
    theme_root = (BASE_DIR / str(settings.themes_select)).resolve()
    try:
        theme_root.relative_to(themes_root)
    except ValueError:
        theme_root = (BASE_DIR / DEFAULT_CONFIG["themes_select"]).resolve()
    if not theme_root.exists():
        theme_root = (BASE_DIR / DEFAULT_CONFIG["themes_select"]).resolve()
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


@router.get("/assets/{asset_path:path}", include_in_schema=False)
async def theme_asset(asset_path: str):
    return FileResponse(resolve_theme_file("assets", asset_path))


@router.get("/")
async def index(request=None, exc=None):
    # Site config is admin input (and during the setup window anyone can claim it);
    # always escape before injecting into the theme template to prevent stored XSS
    # (mirrors the setup page).
    return HTMLResponse(
        content=resolve_theme_file("index.html")
        .read_text(encoding="utf-8")
        .replace("{{title}}", html.escape(str(settings.name)))
        .replace("{{description}}", html.escape(str(settings.description)))
        .replace("{{keywords}}", html.escape(str(settings.keywords)))
        .replace("{{opacity}}", html.escape(str(settings.opacity)))
        .replace("{{background}}", html.escape(str(settings.background))),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )

@router.get("/robots.txt")
async def robots():
    return HTMLResponse(content=settings.robots_text, media_type="text/plain")


@router.post("/")
async def get_config():
    return APIResponse(detail=build_public_config())


@router.get("/api/v1/config")
async def get_public_config():
    return APIResponse(
        detail={
            "config": build_public_config(),
            "meta": build_public_meta(),
        }
    )


@router.get("/health")
async def health_check():
    return APIResponse(
        detail={
            "status": "ok",
            "version": APP_VERSION,
            "storage": settings.file_storage,
            "theme": settings.themes_select,
        }
    )
