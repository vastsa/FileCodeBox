import datetime
import os
import uuid
import threading
import random

from fastapi import FastAPI, Depends, UploadFile, Form, File
from starlette.requests import Request
from starlette.responses import HTMLResponse
from starlette.staticfiles import StaticFiles

from sqlalchemy import or_, select, update, delete, create_engine
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio.session import AsyncSession

from database import engine, get_session, Base, Codes


engine = create_engine('sqlite:///database.db', connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)

app = FastAPI()
if not os.path.exists('./static'):
    os.makedirs('./static')
app.mount("/static", StaticFiles(directory="static"), name="static")

############################################
# 需要修改的参数
# 允许错误次数
error_count = 5
# 禁止分钟数
error_minute = 10
# 后台地址
admin_address = 'admin'
# 管理密码
admin_password = 'admin'
# 文件大小限制 10M
file_size_limit = 1024 * 1024 * 10
# 系统标题
title = '文件快递柜'
# 系统描述
description = 'FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件，图片，视频，音频，压缩包等文件'
# 系统关键字
keywords = 'FileCodeBox，文件快递柜，口令传送箱，匿名口令分享文本，文件，图片，视频，音频，压缩包等文件'
############################################

index_html = open('templates/index.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', title) \
    .replace('{{description}}', description) \
    .replace('{{keywords}}', keywords)
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read() \
    .replace('{{title}}', title) \
    .replace('{{description}}', description) \
    .replace('{{keywords}}', keywords)

error_ip_count = {}


def delete_file(files):
    for file in files:
        if file['type'] != 'text':
            os.remove('.' + file['text'])


async def get_code(s: AsyncSession):
    code = random.randint(10000, 99999)
    while (await s.execute(select(Codes.id).where(Codes.code == code))).scalar():
        code = random.randint(10000, 99999)
    return str(code)


def get_file_name(key, ext, file):
    now = datetime.datetime.now()
    file_bytes = file.file.read()
    size = len(file_bytes)
    if size > file_size_limit:
        return size, '', '', ''
    path = f'./static/upload/{now.year}/{now.month}/{now.day}/'
    name = f'{key}.{ext}'
    if not os.path.exists(path):
        os.makedirs(path)
    with open(f'{os.path.join(path, name)}', 'wb') as f:
        f.write(file_bytes)
    return size, path[1:] + name, file.content_type, file.filename


@app.get(f'/{admin_address}')
async def admin():
    return HTMLResponse(admin_html)


@app.post(f'/{admin_address}')
async def admin_post(request: Request, s: AsyncSession = Depends(get_session)):
    if request.headers.get('pwd') == admin_password:
        query = select(Codes)
        codes = (await s.execute(query)).scalars().all()
        return {'code': 200, 'msg': '查询成功', 'data': codes}
    else:
        return {'code': 404, 'msg': '密码错误'}


@app.delete(f'/{admin_address}')
async def admin_delete(request: Request, code: str, s: AsyncSession = Depends(get_session)):
    if request.headers.get('pwd') == admin_password:
        query = select(Codes).where(Codes.code == code)
        file = (await s.execute(query)).scalars().first()
        threading.Thread(target=delete_file, args=([{'type': file.type, 'text': file.text}],)).start()
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
        if error_ip_count[ip]['count'] >= error_count:
            if error_ip_count[ip]['time'] + datetime.timedelta(minutes=error_minute) > datetime.datetime.now():
                return False
            else:
                error_ip_count.pop(ip)
    return True


def ip_error(ip):
    ip_info = error_ip_count.get(ip, {'count': 0, 'time': datetime.datetime.now()})
    ip_info['count'] += 1
    error_ip_count[ip] = ip_info
    return ip_info['count']


@app.post('/')
async def index(request: Request, code: str, s: AsyncSession = Depends(get_session)):
    ip = request.client.host
    if not check_ip(ip):
        return {'code': 404, 'msg': '错误次数过多，请稍后再试'}
    query = select(Codes).where(Codes.code == code)
    info = (await s.execute(query)).scalars().first()
    if not info:
        return {'code': 404, 'msg': f'取件码错误，错误{error_count - ip_error(ip)}次将被禁止10分钟'}
    if info.exp_time < datetime.datetime.now() or info.count == 0:
        threading.Thread(target=delete_file, args=([{'type': info.type, 'text': info.text}],)).start()
        await s.delete(info)
        await s.commit()
        return {'code': 404, 'msg': '取件码已过期，请联系寄件人'}

    count = info.count - 1
    query = update(Codes).where(Codes.id == info.id).values(count=count)
    await s.execute(query)
    await s.commit()
    return {
        'code': 200,
        'msg': '取件成功，请点击"取"查看',
        'data': {'type': info.type, 'text': info.text, 'name': info.name, 'code': info.code}
    }


@app.post('/share')
async def share(text: str = Form(default=None), style: str = Form(default='2'), value: int = Form(default=1),
                file: UploadFile = File(default=None), s: AsyncSession = Depends(get_session)):
    query = select(Codes).where(or_(Codes.exp_time < datetime.datetime.now(), Codes.count == 0))
    exps = (await s.execute(query)).scalars().all()
    threading.Thread(target=delete_file, args=([[{'type': old.type, 'text': old.text}] for old in exps],)).start()
    
    exps_ids = [exp.id for exp in exps]
    query = delete(Codes).where(Codes.id.in_(exps_ids))
    await s.execute(query)
    await s.commit()

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
        size, _text, _type, name = get_file_name(key, file.filename.split('.')[-1], file)
        if size > file_size_limit:
            return {'code': 404, 'msg': '文件过大'}
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
