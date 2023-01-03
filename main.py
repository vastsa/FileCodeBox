import datetime
import uuid
import asyncio
from pathlib import Path
import os
try:
    import chardet
    from fastapi import FastAPI, Depends, UploadFile, Form, File, HTTPException, BackgroundTasks
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, FileResponse
    from starlette.staticfiles import StaticFiles
    from sqlalchemy import select, update, func
    from sqlalchemy.ext.asyncio.session import AsyncSession
except ImportError:
    os.system("pip install -r requirements.txt")
    import chardet
    from fastapi import FastAPI, Depends, UploadFile, Form, File, HTTPException, BackgroundTasks
    from starlette.requests import Request
    from starlette.responses import HTMLResponse, FileResponse
    from starlette.staticfiles import StaticFiles
    from sqlalchemy import select, update, func
    from sqlalchemy.ext.asyncio.session import AsyncSession

import settings
from utils import delete_expire_files, storage, get_code, error_ip_limit, upload_ip_limit
from database import get_session, Codes, init_models, Values
from depends import admin_required

# 实例化FastAPI
app = FastAPI(debug=settings.DEBUG, docs_url=None, redoc_url=None)

# 数据存储文件夹
DATA_ROOT = Path(settings.DATA_ROOT)
if not DATA_ROOT.exists():
    DATA_ROOT.mkdir(parents=True)

# 静态文件夹，这个固定就行了，静态资源都放在这里
app.mount(settings.STATIC_URL, StaticFiles(directory='./static'), name="static")


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
    .replace('{{keywords}}', settings.KEYWORDS) \
    .replace("'{{fileSizeLimit}}'", str(settings.FILE_SIZE_LIMIT)) \
    # 管理页面
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', settings.TITLE) \
    .replace('{{description}}', settings.DESCRIPTION) \
    .replace('{{keywords}}', settings.KEYWORDS)


@app.get(f'/{settings.ADMIN_ADDRESS}', description='管理页面')
async def admin():
    return HTMLResponse(admin_html)


@app.post(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='查询数据库列表')
async def admin_post(page: int = Form(default=1), size: int = Form(default=10), s: AsyncSession = Depends(get_session)):
    codes = (await s.execute(select(Codes).offset((page - 1) * size).limit(size))).scalars().all()
    total = (await s.execute(select(func.count(Codes.id)))).scalar()
    return {'detail': '查询成功', 'data': codes, 'paginate': {
        'page': page,
        'size': size,
        'total': total
    }}


@app.patch(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='修改数据库数据')
async def admin_patch(request: Request, s: AsyncSession = Depends(get_session)):
    # 从数据库获取系统配置
    # 如果不存在config这个key，就创建一个
    config = (await s.execute(select(Values).filter(Values.key == 'config'))).scalar_one_or_none()
    if not config:
        s.add(Values(key='config', value=await request.json()))
    else:
        await s.execute(update(Values).where(Values.key == 'config').values(value=await request.json()))
    await s.commit()
    return {'detail': '修改成功'}


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


@app.get('/config', description='获取系统配置', dependencies=[Depends(admin_required)])
async def config(s: AsyncSession = Depends(get_session)):
    # 从数据库获取系统配置
    data = (await s.execute(select(Values).filter(Values.key == 'config'))).scalar_one_or_none()
    return {'detail': '获取成功', 'data': data.value if data else {'banners': []}}


@app.get('/')
async def index():
    return HTMLResponse(index_html)


@app.get('/banner')
async def banner(request: Request, s: AsyncSession = Depends(get_session)):
    # 数据库查询config
    config = (await s.execute(select(Values).filter(Values.key == 'config'))).scalar_one_or_none()
    # 如果存在config，就返回config的value
    if config and config.value.get('banners'):
        return {
            'detail': '查询成功',
            'data': config.value['banners'],
            'enable': request.headers.get('pwd', '') == settings.ADMIN_PASSWORD or settings.ENABLE_UPLOAD,
        }
    # 如果不存在config，就返回默认的banner
    return {
        'detail': 'banner',
        'enable': request.headers.get('pwd', '') == settings.ADMIN_PASSWORD or settings.ENABLE_UPLOAD,
        'data': [{
            'text': 'FileCodeBox',
            'url': 'https://github.com/vastsa/FileCodeBox',
            'src': '/static/banners/img_1.png'
        }, {
            'text': 'FileCodeBox',
            'url': 'https://www.lanol.cn',
            'src': '/static/banners/img_2.png'
        }]
    }


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
        raise HTTPException(status_code=404, detail="取件码已失效，请联系寄件人")
    await s.execute(update(Codes).where(Codes.id == info.id).values(count=info.count - 1))
    await s.commit()
    if info.type != 'text':
        info.text = f'/select?code={code}'
    return {
        'detail': f'取件成功，文件将在{settings.DELETE_EXPIRE_FILES_INTERVAL}分钟后删除',
        'data': {'type': info.type, 'text': info.text, 'name': info.name, 'code': info.code}
    }


@app.post('/share', dependencies=[Depends(admin_required)], description='分享文件')
async def share(background_tasks: BackgroundTasks, text: str = Form(default=None),
                style: str = Form(default='2'), value: int = Form(default=1), file: UploadFile = File(default=None),
                ip: str = Depends(upload_ip_limit), s: AsyncSession = Depends(get_session)):
    code = await get_code(s)
    if style == '2':
        if value > settings.MAX_DAYS:
            raise HTTPException(status_code=400, detail=f"最大有效天数为{settings.MAX_DAYS}天")
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
        'data': {'code': code, 'key': key, 'name': name}
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=settings.PORT, reload=settings.DEBUG)
