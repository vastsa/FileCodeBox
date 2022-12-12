import datetime
import uuid
import random
import asyncio
from pathlib import Path

from fastapi import FastAPI, Depends, UploadFile, Form, File
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse
from starlette.staticfiles import StaticFiles

from sqlalchemy import or_, select, update, delete
from sqlalchemy.ext.asyncio.session import AsyncSession

import settings
from database import get_session, Codes, init_models, engine
from storage import STORAGE_ENGINE

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

error_ip_count = {}


async def delete_expire_files():
    while True:
        async with AsyncSession(engine, expire_on_commit=False) as s:
            query = select(Codes).where(or_(Codes.exp_time < datetime.datetime.now(), Codes.count == 0))
            exps = (await s.execute(query)).scalars().all()
            files = [{'type': old.type, 'text': old.text} for old in exps]
            await storage.delete_files(files)
            exps_ids = [exp.id for exp in exps]
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


@app.post(f'/{settings.ADMIN_ADDRESS}')
async def admin_post(request: Request, s: AsyncSession = Depends(get_session)):
    if request.headers.get('pwd') == settings.ADMIN_PASSWORD:
        query = select(Codes)
        codes = (await s.execute(query)).scalars().all()
        return {'code': 200, 'msg': '查询成功', 'data': codes}
    else:
        return {'code': 404, 'msg': '密码错误'}


@app.delete(f'/{settings.ADMIN_ADDRESS}')
async def admin_delete(request: Request, code: str, s: AsyncSession = Depends(get_session)):
    if request.headers.get('pwd') == settings.ADMIN_PASSWORD:
        query = select(Codes).where(Codes.code == code)
        file = (await s.execute(query)).scalars().first()
        await storage.delete_file({'type': file.type, 'text': file.text})
        await s.delete(file)
        await s.commit()
        return {'code': 200, 'msg': '删除成功'}
    else:
        return {'code': 404, 'msg': '密码错误'}


@app.get('/')
async def index():
    return HTMLResponse(index_html)


def check_ip(ip):
    # 检查ip是否被禁止
    if ip in error_ip_count:
        if error_ip_count[ip]['count'] >= settings.ERROR_COUNT:
            if error_ip_count[ip]['time'] + datetime.timedelta(minutes=settings.ERROR_MINUTE) > datetime.datetime.now():
                return False
            else:
                error_ip_count.pop(ip)
    return True


def ip_error(ip):
    ip_info = error_ip_count.get(ip, {'count': 0, 'time': datetime.datetime.now()})
    ip_info['count'] += 1
    error_ip_count[ip] = ip_info
    return ip_info['count']


@app.get('/select')
async def get_file(code: str, s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if info:
        if info.type == 'text':
            return {'code': code, 'msg': '查询成功', 'data': info.text}
        else:
            filepath = await storage.get_filepath(info.text)
            return FileResponse(filepath, filename=info.name)
    else:
        return {'code': 404, 'msg': '口令不存在'}


@app.post('/')
async def index(request: Request, code: str, s: AsyncSession = Depends(get_session)):
    ip = request.client.host
    if not check_ip(ip):
        return {'code': 404, 'msg': '错误次数过多，请稍后再试'}
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        return {'code': 404, 'msg': f'取件码错误，错误{settings.ERROR_COUNT - ip_error(ip)}次将被禁止10分钟'}
    if info.exp_time < datetime.datetime.now() or info.count == 0:
        await storage.delete_file({'type': info.type, 'text': info.text})
        await s.delete(info)
        await s.commit()
        return {'code': 404, 'msg': '取件码已过期，请联系寄件人'}
    count = info.count - 1
    query = update(Codes).where(Codes.id == info.id).values(count=count)
    await s.execute(query)
    await s.commit()
    if info.type != 'text':
        info.text = f'/select?code={code}'
    return {
        'code': 200,
        'msg': '取件成功，请点击"取"查看',
        'data': {'type': info.type, 'text': info.text, 'name': info.name, 'code': info.code}
    }


@app.post('/share')
async def share(text: str = Form(default=None), style: str = Form(default='2'), value: int = Form(default=1),
                file: UploadFile = File(default=None), s: AsyncSession = Depends(get_session)):
    code = await get_code(s)
    if style == '2':
        if value > 7:
            return {'code': 404, 'msg': '最大有效天数为7天'}
        exp_time = datetime.datetime.now() + datetime.timedelta(days=value)
        exp_count = -1
    elif style == '1':
        if value < 1:
            return {'code': 404, 'msg': '最小有效次数为1次'}
        exp_time = datetime.datetime.now() + datetime.timedelta(days=1)
        exp_count = value
    else:
        exp_time = datetime.datetime.now() + datetime.timedelta(days=1)
        exp_count = -1
    key = uuid.uuid4().hex
    if file:
        file_bytes = await file.read()
        size = len(file_bytes)
        if size > settings.FILE_SIZE_LIMIT:
            return {'code': 404, 'msg': '文件过大'}
        _text, _type, name = await storage.save_file(file, file_bytes, key), file.content_type, file.filename
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
        'code': 200,
        'msg': '分享成功，请点击文件箱查看取件码',
        'data': {'code': code, 'key': key, 'name': name, 'text': _text}
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=12345)
