from typing import Union
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request

import settings


async def admin_required(pwd: Union[str, None] = Header(default=None)):
    if not pwd or pwd != settings.ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="密码错误")


class IPRateLimit:
    ips = {}

    def check_ip(self, ip):
        # 检查ip是否被禁止
        if ip in self.ips:
            if self.ips[ip]['count'] >= settings.ERROR_COUNT:
                if self.ips[ip]['time'] + timedelta(minutes=settings.ERROR_MINUTE) > datetime.now():
                    return False
                else:
                    self.ips.pop(ip)
        return True
    
    def add_ip(cls, ip):
        ip_info = cls.ips.get(ip, {'count': 0, 'time': datetime.now()})
        ip_info['count'] += 1
        cls.ips[ip] = ip_info
        return ip_info['count']
    
    def __call__(self, request: Request):
        ip = request.client.host
        if not self.check_ip(ip):
            raise HTTPException(status_code=400, detail="错误次数过多，请稍后再试")
        return ip
