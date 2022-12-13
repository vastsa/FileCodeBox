import datetime
import uuid
import random
import asyncio
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, Form, File, HTTPException, BackgroundTasks
from starlette.responses import HTMLResponse, FileResponse
from starlette.staticfiles import StaticFiles

from sqlalchemy import or_, select, update, delete
from sqlalchemy.ext.asyncio.session import AsyncSession

import settings
from database import get_session, Codes, init_models, engine
from storage import STORAGE_ENGINE
from depends import admin_required, IPRateLimit

app = FastAPI(debug=settings.DEBUG)

DATA_ROOT = Path(settings.DATA_ROOT)
if not DATA_ROOT.exists():
    DATA_ROOT.mkdir(parents=True)

STATIC_URL = settings.STATIC_URL
app.mount(STATIC_URL, StaticFiles(directory=DATA_ROOT), name="static")

storage = STORAGE_ENGINE[settings.STORAGE_ENGINE]()


@app.on_event('startup')
async def startup():
    await init_models()
    asyncio.create_task(delete_expire_files())


index_html = open('templates/index.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', settings.TITLE) \
    .replace('{{description}}', settings.DESCRIPTION) \
    .replace('{{keywords}}', settings.KEYWORDS)
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', settings.TITLE) \
    .replace('{{description}}', settings.DESCRIPTION) \
    .replace('{{keywords}}', settings.KEYWORDS)

ip_limit = IPRateLimit()


async def delete_expire_files():
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            query = select(Codes).where(or_(Codes.exp_time < datetime.datetime.now(), Codes.count == 0))
            exps = (await s.execute(query)).scalars().all()
            files = []
            exps_ids = []
            for exp in exps:
                if exp.type != "text":
                    files.append(exp.text)
                exps_ids.append(exp.id)
            await storage.delete_files(files)
            query = delete(Codes).where(Codes.id.in_(exps_ids))
            await s.execute(query)
            await s.commit()
        await asyncio.sleep(random.randint(60, 300))


async def get_code(s: AsyncSession):
    code = random.randint(10000, 99999)
    while (await s.execute(select(Codes.id).where(Codes.code == code))).scalar():
        code = random.randint(10000, 99999)
    return str(code)


@app.get(f'/{settings.ADMIN_ADDRESS}')
async def admin():
    return HTMLResponse(admin_html)


@app.post(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)])
async def admin_post(s: AsyncSession = Depends(get_session)):
    query = select(Codes)
    codes = (await s.execute(query)).scalars().all()
    return {'detail': '查询成功', 'data': codes}


@app.delete(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)])
async def admin_delete(code: str, s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    file = (await s.execute(query)).scalars().first()
    if file:
        if file.type != 'text':
            await storage.delete_file(file.text)
        await s.delete(file)
        await s.commit()
    return {'detail': '删除成功'}


@app.get('/')
async def index():
    return HTMLResponse(index_html)


@app.get('/select')
async def get_file(code: str, s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        raise HTTPException(status_code=404, detail="口令不存在")
    if info.type == 'text':
        return {'detail': '查询成功', 'data': info.text}
    else:
        filepath = await storage.get_filepath(info.text)
        return FileResponse(filepath, filename=info.name)


@app.post('/')
async def index(code: str, ip: str = Depends(ip_limit), s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        error_count = settings.ERROR_COUNT - ip_limit.add_ip(ip)
        raise HTTPException(status_code=404, detail=f"取件码错误，错误{error_count}次将被禁止10分钟")
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
                value: int = Form(default=1), file: UploadFile = File(default=None), s: AsyncSession = Depends(get_session)):
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
    info = Codes(
        code=code,
        text=_text,
        size=size,
        type=_type,
        name=name,
        count=exp_count,
        exp_time=exp_time,
        key=key
    )
    s.add(info)
    await s.commit()
    return {
        'detail': '分享成功，请点击文件箱查看取件码',
        'data': {'code': code, 'key': key, 'name': name, 'text': _text}
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=settings.PORT, debug=settings.DEBUG)
