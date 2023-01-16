from typing import Union
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request

from settings import settings


async def admin_required(pwd: Union[str, None] = Header(default=None), request: Request = None):
    if 'share' in request.url.path:
        if pwd != settings.ADMIN_PASSWORD and not settings.ENABLE_UPLOAD:
            raise HTTPException(status_code=403, detail='本站上传功能已关闭，仅管理员可用')
    else:
        print(settings.ADMIN_PASSWORD)
        if settings.ADMIN_PASSWORD is None:
            raise HTTPException(status_code=404, detail='您未设置管理员密码，无法使用此功能，请更新配置文件后，重启系统')
        if not pwd or pwd != settings.ADMIN_PASSWORD:
            raise HTTPException(status_code=401, detail="密码错误，请重新登录")


class IPRateLimit:
    def __init__(self, count, minutes):
        self.ips = {}
        self.count = count
        self.minutes = minutes

    def check_ip(self, ip):
        # 检查ip是否被禁止
        if ip in self.ips:
            if self.ips[ip]['count'] >= self.count:
                if self.ips[ip]['time'] + timedelta(minutes=self.minutes) > datetime.now():
                    return False
                else:
                    self.ips.pop(ip)
        return True

    def add_ip(self, ip):
        ip_info = self.ips.get(ip, {'count': 0, 'time': datetime.now()})
        ip_info['count'] += 1
        self.ips[ip] = ip_info
        return ip_info['count']

    async def remove_expired_ip(self):
        for ip in list(self.ips.keys()):
            if self.ips[ip]['time'] + timedelta(minutes=self.minutes) < datetime.now():
                self.ips.pop(ip)

    def __call__(self, request: Request):
        ip = request.headers.get('X-Real-IP', request.headers.get('X-Forwarded-For', request.client.host))
        if not self.check_ip(ip):
            raise HTTPException(status_code=400, detail=f"请求次数过多，请稍后再试")
        return ip
