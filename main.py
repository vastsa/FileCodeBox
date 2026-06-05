# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from apps.admin.views import admin_api
from apps.base.models import KeyValue
from apps.base.utils import ip_limit
from apps.base.views import share_api, chunk_api, presign_api
from core.config import ensure_settings_row, refresh_settings
from core.database import db_startup_lock, get_db_config, init_db
from core.logger import logger
from core.response import APIResponse
from core.settings import settings, BASE_DIR, DEFAULT_CONFIG
from core.tasks import delete_expire_files, clean_incomplete_uploads
from core.utils import hash_password, is_password_hashed
from core.version import APP_VERSION


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
        "show_admin_address": settings.showAdminAddr,
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
            "adminAddressVisible": bool(settings.showAdminAddr),
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
    logger.info("应用初始化完成")

    try:
        yield
    finally:
        # 清理操作
        logger.info("正在关闭应用...")
        task.cancel()
        chunk_cleanup_task.cancel()
        await asyncio.gather(task, chunk_cleanup_task, return_exceptions=True)
        await Tortoise.close_connections()
        logger.info("应用已关闭")


async def load_config():
    await ensure_settings_row()
    await KeyValue.update_or_create(
        key="sys_start", defaults={"value": int(time.time() * 1000)}
    )
    await refresh_settings()

    await migrate_password_to_hash()

    ip_limit["error"].minutes = settings.errorMinute
    ip_limit["error"].count = settings.errorCount
    ip_limit["upload"].minutes = settings.uploadMinute
    ip_limit["upload"].count = settings.uploadCount


async def migrate_password_to_hash():
    if not is_password_hashed(settings.admin_token):
        hashed = hash_password(settings.admin_token)
        settings.admin_token = hashed
        config_record = await KeyValue.filter(key="settings").first()
        if config_record and config_record.value:
            config_record.value["admin_token"] = hashed
            await config_record.save()
            logger.info("已将管理员密码迁移为哈希存储")


app = FastAPI(lifespan=lifespan)

@app.middleware("http")
async def refresh_settings_middleware(request, call_next):
    await refresh_settings()
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
