import datetime
import os
import uuid

from fastapi import FastAPI, Depends, UploadFile, Form, File
from sqlalchemy.orm import Session
from starlette.requests import Request
from starlette.responses import HTMLResponse
import random

from starlette.staticfiles import StaticFiles

import database
from database import engine, SessionLocal, Base

Base.metadata.create_all(bind=engine)
app = FastAPI()
if not os.path.exists('./static'):
    os.makedirs('./static')
app.mount("/static", StaticFiles(directory="static"), name="static")
index_html = open('templates/index.html', 'r', encoding='utf-8').read()
admin_html = open('templates/admin.html', 'r', encoding='utf-8').read()
# 过期时间
exp_hour = 24
# 允许错误次数
error_count = 5
# 禁止分钟数
error_minute = 60
# 后台地址
admin_address = 'admin'
# 管理密码
admin_password = 'admin'
error_ip_count = {}


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_code(db: Session = Depends(get_db)):
    code = random.randint(10000, 99999)
    while db.query(database.Codes).filter(database.Codes.code == code).first():
        code = random.randint(10000, 99999)
    return str(code)


def get_file_name(key, ext, file):
    now = datetime.datetime.now()
    path = f'./static/upload/{now.year}/{now.month}/{now.day}/'
    name = f'{key}.{ext}'
    if not os.path.exists(path):
        os.makedirs(path)
    file = file.file.read()
    with open(f'{os.path.join(path, name)}', 'wb') as f:
        f.write(file)
    return key, len(file), path[1:] + name


@app.get(f'/{admin_address}')
async def admin():
    return HTMLResponse(admin_html)


@app.post(f'/{admin_address}')
async def admin_post(request: Request, db: Session = Depends(get_db)):
    if request.headers.get('pwd') == admin_password:
        codes = db.query(database.Codes).all()
        return {'code': 200, 'msg': '查询成功', 'data': codes}
    else:
        return {'code': 400, 'msg': '密码错误'}


@app.delete(f'/{admin_address}')
async def admin_delete(request: Request, code: str, db: Session = Depends(get_db)):
    if request.headers.get('pwd') == admin_password:
        file = db.query(database.Codes).filter(database.Codes.code == code)
        if file.first().type != 'text/plain':
            os.remove('.' + file.first().text)
        file.delete()
        db.commit()
        return {'code': 200, 'msg': '删除成功'}
    else:
        return {'code': 400, 'msg': '密码错误'}


@app.get('/')
async def index():
    return HTMLResponse(index_html)


@app.post('/')
async def index(request: Request, code: str, db: Session = Depends(get_db)):
    info = db.query(database.Codes).filter(database.Codes.code == code).first()
    error = error_ip_count.get(request.client.host, {'count': 0, 'time': datetime.datetime.now()})
    if error['count'] > error_count:
        if datetime.datetime.now() - error['time'] < datetime.timedelta(minutes=error_minute):
            return {'code': 404, 'msg': '请求过于频繁，请稍后再试'}
        else:
            error['count'] = 0
    else:
        if not info:
            error['count'] += 1
            error_ip_count[request.client.host] = error
            return {'code': 404, 'msg': f'取件码错误，错误5次将被禁止10分钟'}
        else:
            return {'code': 200, 'msg': '取件成功，请点击“取”查看', 'data': info}


@app.post('/share')
async def share(text: str = Form(default=None), file: UploadFile = File(default=None), db: Session = Depends(get_db)):
    cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=exp_hour)
    db.query(database.Codes).filter(database.Codes.use_time < cutoff_time).delete()
    db.commit()
    code = get_code(db)
    if text:
        info = database.Codes(
            code=code,
            text=text,
            type='text/plain',
            key=uuid.uuid4().hex,
            size=len(text),
            used=True,
            name='分享文本'
        )
        db.add(info)
        db.commit()
        return {'code': 200, 'msg': '上传成功，请点击文件库查看',
                'data': {'code': code, 'name': '分享文本', 'text': text}}
    elif file:
        key, size, full_path = get_file_name(uuid.uuid4().hex, file.filename.split('.')[-1], file)
        info = database.Codes(
            code=code,
            text=full_path,
            type=file.content_type,
            key=key,
            size=size,
            used=True,
            name=file.filename
        )
        db.add(info)
        db.commit()
        return {'code': 200, 'msg': '上传成功，请点击文件库查看',
                'data': {'code': code, 'name': file.filename, 'text': full_path}}
    else:
        return {'code': 422, 'msg': '参数错误', 'data': []}
