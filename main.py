# @Time    : 2023/8/9 23:23
# @Author  : Lan
# @File    : main.py
# @Software: PyCharm
import asyncio
import time

from fastapi import FastAPI

from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from tortoise.contrib.fastapi import register_tortoise

from apps.base.models import KeyValue
from apps.base.utils import ip_limit
from apps.base.views import share_api, chunk_api
from apps.admin.views import admin_api
from core.database import init_db
from core.response import APIResponse
from core.settings import data_root, settings, BASE_DIR, DEFAULT_CONFIG
from core.tasks import delete_expire_files
from core.logger import logger

from contextlib import asynccontextmanager
from tortoise import Tortoise


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("正在初始化应用...")
    # 初始化数据库
    await init_db()

    # 加载配置
    await load_config()
    app.mount(
        "/assets",
        StaticFiles(directory=f"./{settings.themesSelect}/assets"),
        name="assets",
    )

    # 启动后台任务
    task = asyncio.create_task(delete_expire_files())
    logger.info("应用初始化完成")

    try:
        yield
    finally:
        # 清理操作
        logger.info("正在关闭应用...")
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        await Tortoise.close_connections()
        logger.info("应用已关闭")


async def load_config():
    user_config, _ = await KeyValue.get_or_create(
        key="settings", defaults={"value": DEFAULT_CONFIG}
    )
    await KeyValue.update_or_create(
        key="sys_start", defaults={"value": int(time.time() * 1000)}
    )
    settings.user_config = user_config.value
    # 更新 ip_limit 配置
    ip_limit["error"].minutes = settings.errorMinute
    ip_limit["error"].count = settings.errorCount
    ip_limit["upload"].minutes = settings.uploadMinute
    ip_limit["upload"].count = settings.uploadCount


app = FastAPI(lifespan=lifespan)

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
    config={
        "connections": {"default": f"sqlite://{data_root}/filecodebox.db"},
        "apps": {
            "models": {
                "models": ["apps.base.models"],
                "default_connection": "default",
            },
        },
    },
    generate_schemas=False,
    add_exception_handlers=True,
)

app.include_router(share_api)
app.include_router(chunk_api)
app.include_router(admin_api)


@app.exception_handler(404)
@app.get("/")
async def index(request=None, exc=None):
    return HTMLResponse(
        content=open(
            BASE_DIR / f"{settings.themesSelect}/index.html", "r", encoding="utf-8"
        )
        .read()
        .replace("{{title}}", str(settings.name))
        .replace("{{description}}", str(settings.description))
        .replace("{{keywords}}", str(settings.keywords))
        .replace("{{opacity}}", str(settings.opacity))
        .replace('"/assets/', '"assets/')
        .replace("{{background}}", str(settings.background)),
        media_type="text/html",
        headers={"Cache-Control": "no-cache"},
    )


@app.get("/robots.txt")
async def robots():
    return HTMLResponse(content=settings.robotsText, media_type="text/plain")


@app.post("/")
async def get_config():
    return APIResponse(
        detail={
            "name": settings.name,
            "description": settings.description,
            "explain": settings.page_explain,
            "uploadSize": settings.uploadSize,
            "expireStyle": settings.expireStyle,
            "enableChunk": settings.enableChunk if settings.file_storage == "local" and settings.enableChunk else 0,
            "openUpload": settings.openUpload,
            "notify_title": settings.notify_title,
            "notify_content": settings.notify_content,
            "show_admin_address": settings.showAdminAddr,
            "max_save_seconds": settings.max_save_seconds,
        }
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app="main:app", host="0.0.0.0", port=settings.port, reload=False, workers=1
    )
