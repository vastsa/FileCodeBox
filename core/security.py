import copy
import ipaddress
import os
import secrets
import socket
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

from core.utils import hash_password, is_password_hashed, verify_password


JWT_SECRET_MIN_LENGTH = 32
INTERNAL_CONFIG_KEYS = {"jwt_secret"}
LEGACY_DEFAULT_ADMIN_TOKEN = "FileCodeBox" + "2023"


@dataclass
class SecurityConfigResult:
    config: dict[str, Any]
    changed: bool = False
    password_hashed: bool = False
    jwt_secret_rotated: bool = False
    setup_required: bool = False


def generate_jwt_secret() -> str:
    return secrets.token_urlsafe(48)


def is_valid_jwt_secret(secret: Any) -> bool:
    return isinstance(secret, str) and len(secret) >= JWT_SECRET_MIN_LENGTH


def is_config_initialized(config: dict[str, Any]) -> bool:
    """Cheap initialization probe — runs on EVERY request via the middleware.

    Must never run a slow hash: a scrypt-stored token cannot be the legacy
    default (which only ever existed as plaintext or sha256), so those tokens
    are initialized without any verification. Only plaintext/sha256 tokens go
    through the legacy-default comparison, which is microseconds.
    """
    admin_token = str(config.get("admin_token") or "")
    if not admin_token:
        return False
    if is_password_hashed(admin_token) and admin_token.startswith("scrypt$"):
        return True
    return not verify_password(LEGACY_DEFAULT_ADMIN_TOKEN, admin_token)


def prepare_security_config(config: dict[str, Any]) -> SecurityConfigResult:
    next_config = copy.deepcopy(config)
    result = SecurityConfigResult(config=next_config)

    admin_token = str(next_config.get("admin_token") or "")
    if not admin_token:
        result.setup_required = True
    elif verify_password(LEGACY_DEFAULT_ADMIN_TOKEN, admin_token):
        next_config["admin_token"] = ""
        result.setup_required = True
        result.changed = True
    elif not is_password_hashed(admin_token):
        next_config["admin_token"] = hash_password(admin_token)
        result.password_hashed = True
        result.changed = True

    jwt_secret = next_config.get("jwt_secret")
    if not is_valid_jwt_secret(jwt_secret):
        next_config["jwt_secret"] = generate_jwt_secret()
        result.jwt_secret_rotated = True
        result.changed = True

    return result


# 出站端点白名单/黑名单（SSRF 防护）。
# 这些配置项会被服务器直接当作上游地址访问：被劫持的管理员会话可以把实例
# 变成内网代理跳板，或把数据发往任意地址。校验只在写入入口（update_config），
# 已存值不受影响；APP_ENV 非 production（本地开发，如 minio/webdav）时放行。
OUTBOUND_ENDPOINT_CONFIG_KEYS = ("s3_endpoint_url", "s3_hostname", "webdav_url")

_ENDPOINT_SCHEME_WHITELIST = {"http", "https"}
_ENDPOINT_HOST_DENY_SUFFIXES = (
    ".local",
    ".internal",
    ".lan",
    ".home.arpa",
    ".corp",
    ".localhost",
)


def _endpoint_ip_is_denied(ip_str: str) -> bool:
    try:
        ip = ipaddress.ip_address(ip_str)
    except ValueError:
        return False
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def _endpoint_host_is_denied(host: str) -> bool:
    host = host.strip("[]").lower()
    if host in {"localhost"} or host.endswith(_ENDPOINT_HOST_DENY_SUFFIXES):
        return True
    # 字面 IP 直接判；非字面形态（速记 "127.1"、十进制 2130706433、十六进制、
    # *.localhost、nip.io 类 DNS 映射）交给解析后逐 IP 复判——静态字符串
    # 黑名单对它们全部失效，这是探测中实测确认的绕过面。
    if _endpoint_ip_is_denied(host):
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError, OSError):
        return False
    for info in infos:
        if _endpoint_ip_is_denied(info[4][0]):
            return True
    return False


def validate_outbound_endpoint(value: Any) -> str:
    """校验完整 URL 形态的出站端点（s3_endpoint_url / webdav_url）。"""
    endpoint = str(value or "").strip()
    if not endpoint:
        return ""

    if os.environ.get("APP_ENV", "development") != "production":
        return endpoint

    parts = urlsplit(endpoint)
    if parts.scheme.lower() not in _ENDPOINT_SCHEME_WHITELIST:
        raise ValueError(f"端点协议必须是 http(s)：{endpoint}")
    host = parts.hostname or ""
    if not host:
        raise ValueError(f"端点缺少主机名：{endpoint}")
    if _endpoint_host_is_denied(host):
        raise ValueError(f"端点不允许指向内网/保留地址：{endpoint}")
    return endpoint


def validate_outbound_hostname(value: Any) -> str:
    """校验裸主机名形态的出站端点（s3_hostname，存储层拼接 https://{hostname}）。"""
    hostname = str(value or "").strip()
    if not hostname:
        return ""

    if os.environ.get("APP_ENV", "development") != "production":
        return hostname

    if "://" in hostname or "/" in hostname:
        raise ValueError(f"s3_hostname 应为裸主机名，不含协议或路径：{hostname}")
    # 取主机部分：[v6] 形态取括号内；host:port 取冒号前；裸 IPv6（多个冒号）整体
    if "[" in hostname:
        host = hostname.split("[", 1)[1].split("]", 1)[0]
        rest = hostname.split("]", 1)[1] if "]" in hostname else ""
        if rest and not rest.startswith(":"):
            raise ValueError(f"s3_hostname 的 IPv6 括号后只允许端口：{hostname}")
    elif hostname.count(":") == 1:
        host = hostname.split(":")[0]
    else:
        host = hostname
    if not host or _endpoint_host_is_denied(host):
        raise ValueError(f"端点不允许指向内网/保留地址：{hostname}")
    return hostname
