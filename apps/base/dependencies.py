import time
from collections import OrderedDict
from ipaddress import ip_address, ip_network
from typing import Iterable, TypedDict
from fastapi import HTTPException, Request

from core.settings import settings


def _iter_trusted_proxies() -> Iterable[str]:
    trusted_proxies = getattr(settings, "trusted_proxies", [])
    if isinstance(trusted_proxies, str):
        trusted_proxies = [item.strip() for item in trusted_proxies.split(",")]
    return [item for item in trusted_proxies if item]


def _is_trusted_proxy(host: str) -> bool:
    try:
        remote_addr = ip_address(host)
    except ValueError:
        return False

    for proxy in _iter_trusted_proxies():
        try:
            if remote_addr in ip_network(proxy, strict=False):
                return True
        except ValueError:
            continue
    return False


def _get_forwarded_for_ip(header_value: str, fallback_ip: str) -> str:
    forwarded_chain = [
        item.strip() for item in header_value.split(",") if item.strip()
    ]
    if not forwarded_chain:
        return fallback_ip

    for candidate in reversed(forwarded_chain):
        try:
            ip_address(candidate)
        except ValueError:
            return fallback_ip
        if not _is_trusted_proxy(candidate):
            return candidate
    return forwarded_chain[0]


def get_client_ip(request: Request) -> str:
    client_host = request.client.host if request.client else "unknown"
    if not _is_trusted_proxy(client_host):
        return client_host

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return _get_forwarded_for_ip(forwarded_for, client_host)

    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        try:
            ip_address(real_ip)
        except ValueError:
            return client_host
        return real_ip

    return client_host


class _IPRecord(TypedDict):
    count: int
    last_seen: float


# Upper bound for tracked source IPs per limiter. Without it a scan using
# spoofed/rotating addresses grows the dict forever on a small VPS.
DEFAULT_MAX_TRACKED_IPS = 10_000


class IPRateLimit:
    def __init__(
        self,
        count: int,
        minutes: int,
        max_ips: int = DEFAULT_MAX_TRACKED_IPS,
    ):
        # Ordered by last activity (oldest first) so capacity eviction and the
        # periodic cleanup are both O(1)/O(expired) instead of a full rebuild.
        self.ips: OrderedDict[str, _IPRecord] = OrderedDict()
        self.count = count
        self.minutes = minutes
        self.max_ips = max(1, max_ips)

    def _window_seconds(self) -> float:
        # minutes is mutable at runtime via apps.base.config._sync_ip_limits.
        return float(self.minutes) * 60

    def check_ip(self, ip: str) -> bool:
        record = self.ips.get(ip)
        if record is None:
            return True
        if record["count"] >= self.count:
            if record["last_seen"] + self._window_seconds() > time.monotonic():
                return False
            self.ips.pop(ip, None)
        return True

    def add_ip(self, ip: str) -> int:
        now = time.monotonic()
        record = self.ips.get(ip)
        if record is None:
            record = {"count": 0, "last_seen": now}
            self.ips[ip] = record
        else:
            self.ips.move_to_end(ip)
        record["count"] += 1
        record["last_seen"] = now
        while len(self.ips) > self.max_ips:
            # Evict the least recently active IP; fail-open for the evicted
            # address is preferable to unbounded memory growth.
            self.ips.popitem(last=False)
        return record["count"]

    async def remove_expired_ip(self) -> None:
        now = time.monotonic()
        window = self._window_seconds()
        while self.ips:
            _, record = next(iter(self.ips.items()))
            if record["last_seen"] + window >= now:
                break
            self.ips.popitem(last=False)

    def __call__(self, request: Request) -> str:
        ip = get_client_ip(request)
        if not self.check_ip(ip):
            raise HTTPException(status_code=423, detail="请求次数过多，请稍后再试")
        return ip
