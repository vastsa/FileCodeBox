from typing import Dict, Union
from datetime import datetime, timedelta
from fastapi import HTTPException, Request


class IPRateLimit:
    def __init__(self, count: int, minutes: int):
        self.ips: Dict[str, Dict[str, Union[int, datetime]]] = {}
        self.count = count
        self.minutes = minutes

    def check_ip(self, ip: str) -> bool:
        if ip in self.ips:
            ip_info = self.ips[ip]
            if ip_info["count"] >= self.count:
                if ip_info["time"] + timedelta(minutes=self.minutes) > datetime.now():
                    return False
                self.ips.pop(ip)
        return True

    def add_ip(self, ip: str) -> int:
        ip_info = self.ips.get(ip, {"count": 0, "time": datetime.now()})
        ip_info["count"] += 1
        ip_info["time"] = datetime.now()
        self.ips[ip] = ip_info
        return ip_info["count"]

    async def remove_expired_ip(self) -> None:
        now = datetime.now()
        expiration = timedelta(minutes=self.minutes)
        self.ips = {
            ip: info
            for ip, info in self.ips.items()
            if info["time"] + expiration >= now
        }

    def __call__(self, request: Request) -> str:
        ip = (
            request.headers.get("X-Real-IP")
            or request.headers.get("X-Forwarded-For")
            or request.client.host
        )
        if not self.check_ip(ip):
            raise HTTPException(status_code=423, detail="请求次数过多，请稍后再试")
        return ip
