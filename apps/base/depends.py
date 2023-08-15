# @Time    : 2023/8/14 12:20
# @Author  : Lan
# @File    : depends.py
# @Software: PyCharm
from typing import Union
from datetime import datetime, timedelta

from fastapi import Header, HTTPException, Request

from core.response import APIResponse


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
        ip_info['time'] = datetime.now()
        self.ips[ip] = ip_info
        return ip_info['count']

    async def remove_expired_ip(self):
        for ip in list(self.ips.keys()):
            if self.ips[ip]['time'] + timedelta(minutes=self.minutes) < datetime.now():
                self.ips.pop(ip)

    def __call__(self, request: Request):
        ip = request.headers.get('X-Real-IP', request.headers.get('X-Forwarded-For', request.client.host))
        if not self.check_ip(ip):
            raise HTTPException(status_code=423, detail=f"请求次数过多，请稍后再试")
        return ip
