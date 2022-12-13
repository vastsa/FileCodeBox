import datetime
import uuid
import asyncio
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, Form, File, HTTPException, BackgroundTasks
from starlette.responses import HTMLResponse, FileResponse
from starlette.staticfiles import StaticFiles

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio.session import AsyncSession

import settings
from utils import delete_expire_files, storage, get_code, error_ip_limit, upload_ip_limit
from database import get_session, Codes, init_models
from depends import admin_required

# 实例化FastAPI
app = FastAPI(debug=settings.DEBUG)

# 数据存储文件夹
DATA_ROOT = Path(settings.DATA_ROOT)
if not DATA_ROOT.exists():
    DATA_ROOT.mkdir(parents=True)
# 静态文件夹
app.mount(settings.STATIC_URL, StaticFiles(directory=DATA_ROOT), name="static")


@app.on_event('startup')
async def startup():
    # 初始化数据库
    await init_models()
    # 启动后台任务，不定时删除过期文件
    asyncio.create_task(delete_expire_files())


# 首页页面
index_html = open('templates/index.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', settings.TITLE) \
    .replace('{{description}}', settings.DESCRIPTION) \
    .replace('{{keywords}}', settings.KEYWORDS)
# 管理页面
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', settings.TITLE) \
    .replace('{{description}}', settings.DESCRIPTION) \
    .replace('{{keywords}}', settings.KEYWORDS)


@app.get(f'/{settings.ADMIN_ADDRESS}', description='管理页面', response_class=HTMLResponse)
async def admin():
    return HTMLResponse(admin_html)


@app.post(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='查询数据库列表')
async def admin_post(s: AsyncSession = Depends(get_session)):
    # 查询数据库列表
    codes = (await s.execute(select(Codes))).scalars().all()
    return {'detail': '查询成功', 'data': codes}


@app.delete(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='删除数据库记录')
async def admin_delete(code: str, s: AsyncSession = Depends(get_session)):
    # 找到相应记录
    query = select(Codes).where(Codes.code == code)
    # 找到第一条记录
    file = (await s.execute(query)).scalars().first()
    # 如果记录存在，并且不是文本
    if file and file.type != 'text':
        # 删除文件
        await storage.delete_file(file.text)
    # 删除数据库记录
    await s.delete(file)
    await s.commit()
    return {'detail': '删除成功'}


@app.get('/')
async def index():
    return HTMLResponse(index_html)


@app.get('/select')
async def get_file(code: str, ip: str = Depends(error_ip_limit), s: AsyncSession = Depends(get_session)):
    # 查出数据库记录
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    # 如果记录不存在，IP错误次数+1
    if not info:
        error_ip_limit.add_ip(ip)
        raise HTTPException(status_code=404, detail="口令不存在，次数过多将被禁止访问")
    # 如果是文本，直接返回
    if info.type == 'text':
        return {'detail': '查询成功', 'data': info.text}
    # 如果是文件，返回文件
    else:
        filepath = await storage.get_filepath(info.text)
        return FileResponse(filepath, filename=info.name)


@app.post('/')
async def index(code: str, ip: str = Depends(error_ip_limit), s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        error_count = settings.ERROR_COUNT - error_ip_limit.add_ip(ip)
        raise HTTPException(status_code=404, detail=f"取件码错误，{error_count}次后将被禁止{settings.ERROR_MINUTE}分钟")
    if info.exp_time < datetime.datetime.now() or info.count == 0:
        if info.type != "text":
            await storage.delete_file(info.text)
        await s.delete(info)
        await s.commit()
        raise HTTPException(status_code=404, detail="取件码已过期，请联系寄件人")
    await s.execute(update(Codes).where(Codes.id == info.id).values(count=info.count - 1))
    await s.commit()
    if info.type != 'text':
        info.text = f'/select?code={code}'
    return {
        'detail': '取件成功，请点击"取"查看',
        'data': {'type': info.type, 'text': info.text, 'name': info.name, 'code': info.code}
    }


@app.post('/share')
async def share(background_tasks: BackgroundTasks, text: str = Form(default=None), style: str = Form(default='2'),
                value: int = Form(default=1), file: UploadFile = File(default=None), ip: str = Depends(upload_ip_limit),
                s: AsyncSession = Depends(get_session)):
    code = await get_code(s)
    if style == '2':
        if value > 7:
            raise HTTPException(status_code=400, detail="最大有效天数为7天")
        exp_time = datetime.datetime.now() + datetime.timedelta(days=value)
        exp_count = -1
    elif style == '1':
        if value < 1:
            raise HTTPException(status_code=400, detail="最小有效次数为1次")
        exp_time = datetime.datetime.now() + datetime.timedelta(days=1)
        exp_count = value
    else:
        exp_time = datetime.datetime.now() + datetime.timedelta(days=1)
        exp_count = -1
    key = uuid.uuid4().hex
    if file:
        size = await storage.get_size(file)
        if size > settings.FILE_SIZE_LIMIT:
            raise HTTPException(status_code=400, detail="文件过大")
        _text, _type, name = await storage.get_text(file, key), file.content_type, file.filename
        background_tasks.add_task(storage.save_file, file, _text)
    else:
        size, _text, _type, name = len(text), text, 'text', '文本分享'
    info = Codes(code=code, text=_text, size=size, type=_type, name=name, count=exp_count, exp_time=exp_time, key=key)
    s.add(info)
    await s.commit()
    upload_ip_limit.add_ip(ip)
    return {
        'detail': '分享成功，请点击取件码按钮查看上传列表',
        'data': {'code': code, 'key': key, 'name': name, 'text': _text}
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=settings.PORT, reload=settings.DEBUG)
