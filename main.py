# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from tortoise import Tortoise
from tortoise.contrib.fastapi import register_tortoise

from apps.admin.views import admin_api
from apps.base.config import (
    ensure_security_settings,
    ensure_settings_row,
    is_runtime_initialized,
    refresh_settings,
)
from apps.base.models import KeyValue
from apps.base.pages import index, router as pages_router
from apps.base.setup_wizard import build_setup_page, is_setup_path, setup_response, wants_html_response
from apps.base.tasks import (
    clean_expired_presign_sessions,
    clean_incomplete_uploads,
    delete_expire_files,
)
from apps.base.views import share_api, chunk_api, presign_api
from core.database import db_startup_lock, get_db_config, init_db
from core.errors import StorageError
from core.logger import get_log_level_name, is_access_log_enabled, logger
from core.settings import settings
from core.version import APP_VERSION


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
    # refresh_settings already syncs every rate limiter (error/metadata/upload/login)
    # via _sync_ip_limits; do not hand-sync a subset here — that once drifted by
    # missing the metadata limiter.
    await refresh_settings(force=True)
    await ensure_security_settings()

    # Rate limiters keep per-process state (apps.base.dependencies.IPRateLimit).
    # With multiple workers each process counts independently, so the effective
    # threshold scales with the worker count and resets on restart.
    if settings.server_workers > 1:
        logger.warning(
            "server_workers=%s：进程内限流在多 worker 下各自独立，阈值将按 worker 数放大；"
            "如需完整限流请使用单 worker（默认）或改造为共享存储限流",
            settings.server_workers,
        )


app = FastAPI(lifespan=lifespan, version=APP_VERSION)


@app.exception_handler(StorageError)
async def storage_error_handler(request, exc: StorageError):
    # Render StorageError exactly like FastAPI renders HTTPException so the
    # framework-free storage layer keeps identical client-visible responses.
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


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
    # 前端使用 Bearer Token，不依赖 Cookie credentials。
    # allow_origins=["*"] 与 allow_credentials=True 组合不符合 CORS 规范。
    allow_credentials=False,
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
app.include_router(pages_router)

# 404 时返回主题首页（index 兼任 exception handler 与 GET / 路由）
app.add_exception_handler(404, index)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="main:app",
        host=settings.server_host,
        port=settings.server_port,
        reload=False,
        workers=settings.server_workers,
        log_level=get_log_level_name(),
        access_log=is_access_log_enabled(),
    )
