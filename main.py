import asyncio
import datetime
import uuid
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy import select, func, update
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from starlette.responses import HTMLResponse, FileResponse, RedirectResponse
from starlette.staticfiles import StaticFiles
from core.utils import error_ip_limit, upload_ip_limit, get_code, storage, delete_expire_files, get_token, \
    get_expire_info
from core.depends import admin_required
from fastapi import FastAPI, Depends, UploadFile, Form, File, HTTPException, BackgroundTasks, Header
from core.database import init_models, Options, Codes, get_session
from settings import settings

# 实例化FastAPI
app = FastAPI(debug=settings.DEBUG, redoc_url=None, )


@app.on_event('startup')
async def startup(s: AsyncSession = Depends(get_session)):
    # 初始化数据库
    await init_models(s)
    # 启动后台任务，不定时删除过期文件
    asyncio.create_task(delete_expire_files())


# 数据存储文件夹
DATA_ROOT = Path(settings.DATA_ROOT)
if not DATA_ROOT.exists():
    DATA_ROOT.mkdir(parents=True)

# 静态文件夹，这个固定就行了，静态资源都放在这里
app.mount('/static', StaticFiles(directory='./static'), name="static")

# 首页页面
index_html = open('templates/index.html', 'r', encoding='utf-8').read()
# 管理页面
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read()


@app.get('/')
async def index():
    return HTMLResponse(
        index_html
        .replace('{{title}}', settings.TITLE)
        .replace('{{description}}', settings.DESCRIPTION)
        .replace('{{keywords}}', settings.KEYWORDS)
        .replace("'{{fileSizeLimit}}'", str(settings.FILE_SIZE_LIMIT))
    )


@app.get(f'/{settings.ADMIN_ADDRESS}', description='管理页面')
async def admin():
    return HTMLResponse(
        admin_html
        .replace('{{title}}', settings.TITLE)
        .replace('{{description}}', settings.DESCRIPTION)
        .replace('{{admin_address}}', settings.ADMIN_ADDRESS)
        .replace('{{keywords}}', settings.KEYWORDS)
    )


@app.post(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='查询数据库列表')
async def admin_post(page: int = Form(default=1), size: int = Form(default=10), s: AsyncSession = Depends(get_session)):
    infos = (await s.execute(select(Codes).offset((page - 1) * size).limit(size))).scalars().all()
    data = [{
        'id': info.id,
        'code': info.code,
        'name': info.name,
        'exp_time': info.exp_time,
        'count': info.count,
        'text': info.text if info.type == 'text' else await storage.get_url(info),
    } for info in infos]
    return {
        'detail': '查询成功',
        'data': data,
        'paginate': {
            'page': page,
            'size': size,
            'total': (await s.execute(select(func.count(Codes.id)))).scalar()
        }}


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


@app.get(f'/{settings.ADMIN_ADDRESS}/config', description='获取系统配置', dependencies=[Depends(admin_required)])
async def config(s: AsyncSession = Depends(get_session)):
    # 查询数据库
    data = {}
    for i in (await s.execute(select(Options))).scalars().all():
        data[i.key] = i.value
    return {'detail': '获取成功', 'data': data, 'menus': [
        {'key': 'INSTALL', 'name': '版本信息'},
        {'key': 'WEBSITE', 'name': '网站设置'},
        {'key': 'SHARE', 'name': '分享设置'},
        {'key': 'BANNERS', 'name': 'Banner'},
    ]}


@app.patch(f'/{settings.ADMIN_ADDRESS}', dependencies=[Depends(admin_required)], description='修改数据库数据')
async def admin_patch(request: Request, s: AsyncSession = Depends(get_session)):
    data = await request.json()
    data.pop('INSTALL')
    for key, value in data.items():
        await s.execute(update(Options).where(Options.key == key).values(value=value))
        await settings.update(key, value)
    await s.commit()
    await settings.updates([[i.id, i.key, i.value] for i in (await s.execute(select(Options))).scalars().all()])
    return {'detail': '修改成功'}


@app.post('/')
async def index(code: str, ip: str = Depends(error_ip_limit), s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        error_count = settings.ERROR_COUNT - error_ip_limit.add_ip(ip)
        raise HTTPException(status_code=404, detail=f"取件码错误，{error_count}次后将被禁止{settings.ERROR_MINUTE}分钟")
    if (info.exp_time and info.exp_time < datetime.datetime.now()) or info.count == 0:
        raise HTTPException(status_code=404, detail="取件码已失效，请联系寄件人")
    await s.execute(update(Codes).where(Codes.id == info.id).values(count=info.count - 1))
    await s.commit()
    if info.type != 'text':
        info.text = f'/select?code={info.code}&token={await get_token(code, ip)}'
    return {
        'detail': f'取件成功，请立即下载，避免失效！',
        'data': {'type': info.type, 'text': info.text, 'name': info.name, 'code': info.code}
    }


@app.get('/banner')
async def banner(request: Request):
    return {
        'detail': '查询成功',
        'data': settings.BANNERS,
        'enable': request.headers.get('pwd', '') == settings.ADMIN_PASSWORD or settings.ENABLE_UPLOAD,
    }


@app.get('/select')
async def get_file(code: str, token: str, ip: str = Depends(error_ip_limit), s: AsyncSession = Depends(get_session)):
    # 验证token
    if token != await get_token(code, ip):
        error_ip_limit.add_ip(ip)
        raise HTTPException(status_code=403, detail="口令错误，或已过期，次数过多将被禁止访问")
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
    elif storage.NAME != 'filesystem':
        # 重定向到文件存储服务器
        return RedirectResponse(await storage.get_url(info))
    else:
        filepath = await storage.get_filepath(info.text)
        return FileResponse(filepath, filename=info.name)


@app.post('/file/create/')
async def create_file():
    # 生成随机字符串
    return {'code': 200, 'data': await storage.create_upload_file()}


@app.post('/file/upload/{file_key}/')
async def upload_file(file_key: str, file: bytes = File(...), chunk_index: int = Form(...),
                      total_chunks: int = Form(...)):
    await storage.save_chunk_file(file_key, file, chunk_index, total_chunks)
    return {'code': 200}


@app.get('/file/merge/{file_key}/')
async def merge_chunks(file_key: str, file_name: str, total_chunks: int):
    return {'code': 200, 'data': await storage.merge_chunks(file_key, file_name, total_chunks)}


class ShareDataModel(BaseModel):
    text: str
    size: int = 0
    exp_style: str
    exp_value: int
    type: str
    name: str
    key: str = uuid.uuid4().hex


@app.post('/share/file/', dependencies=[Depends(admin_required)], description='分享文件')
async def share_file(file_model: ShareDataModel, s: AsyncSession = Depends(get_session),
                     ip: str = Depends(error_ip_limit)):
    exp_error, exp_time, exp_count, code = await get_expire_info(file_model.exp_style, file_model.exp_value, s)
    if exp_error:
        raise HTTPException(status_code=400, detail='过期值异常')
    s.add(Codes(code=code, text=file_model.text, size=file_model.size, type=file_model.type, name=file_model.name,
                count=exp_count, exp_time=exp_time, key=file_model.key))
    await s.commit()
    upload_ip_limit.add_ip(ip)
    return {
        'detail': '分享成功，请点击我的文件按钮查看上传列表',
        'data': {'code': code, 'key': file_model.key, 'name': file_model.name}
    }


@app.post('/share/text/', dependencies=[Depends(admin_required)])
async def share_text(text_model: ShareDataModel, s: AsyncSession = Depends(get_session),
                     ip: str = Depends(error_ip_limit)):
    exp_error, exp_time, exp_count, code = await get_expire_info(text_model.exp_style, text_model.exp_value, s, )
    if exp_error:
        raise HTTPException(status_code=400, detail='过期值异常')
    exp_status, exp_time, exp_count, code = await get_expire_info(text_model.exp_style, text_model.exp_value, s)
    size, _text, _type, name, key = len(text_model.text), text_model.text, 'text', '文本分享', text_model.key
    s.add(Codes(code=code, text=_text, size=size, type=_type, name=name, count=exp_count, exp_time=exp_time, key=key))
    await s.commit()
    upload_ip_limit.add_ip(ip)
    return {
        'detail': '分享成功，请点击我的文件按钮查看上传列表',
        'data': {'code': code, 'key': key, 'name': name}
    }


if __name__ == '__main__':
    import uvicorn

    uvicorn.run('main:app', host='0.0.0.0', port=settings.PORT, reload=settings.DEBUG)
