# @Time    : 2023/8/13 19:54
# @Author  : Lan
# @File    : utils.py
# @Software: PyCharm
import datetime
import hashlib
import hmac
import os
import re
import secrets
import string
import time

from core.settings import settings


async def get_random_num():
    """
    获取随机数
    :return:
    """
    return secrets.randbelow(90000) + 10000


r_s = string.ascii_uppercase + string.digits


def validate_background_url(value) -> str:
    """Validate the site background config before it reaches the theme template.

    Themes inject this value into inline CSS ``url('...')`` where html escaping
    cannot neutralize a single-quote breakout, so only well-formed http(s) URLs
    (or an empty string) are accepted.
    """
    value = str(value or "").strip()
    if not value:
        return ""
    from urllib.parse import urlparse

    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise ValueError("background 必须是 http(s) 完整 URL 或留空")
    # quote()/whitespace would break out of the CSS url('') quoting context
    if any(ch in value for ch in ("'", '"', "(", ")", " ", "\\", ";")):
        raise ValueError("background URL 含有不允许的字符")
    return value


async def get_random_string():
    """
    获取随机字符串
    :return:
    """
    return "".join(secrets.choice(r_s) for _ in range(5))


async def get_now():
    """
    获取当前时间
    :return:
    """
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=8)))


async def get_select_token(code: str, offset: int = 0):
    """
    获取下载token
    :param code: 取件码
    :param offset: 时间窗口偏移（0=当前窗口，1=上一个窗口）。
        用于兼容窗口边界竞态：用户在某窗口末尾获取的 token，
        请求到达服务器时可能已进入下一窗口。
    :return:
    """
    token = getattr(settings, "jwt_secret", "")
    if not token:
        raise RuntimeError("应用签名密钥未初始化")
    # 每个窗口约 1000 秒；offset 允许校验上一窗口，避免边界竞态
    time_factor = int(time.time() / 1000) - max(0, int(offset))
    return hashlib.sha256(
        f"{code}{time_factor}000{token}".encode()
    ).hexdigest()


async def get_file_url(code: str):
    """
    对于需要通过服务器中转下载的服务，获取文件下载地址
    :param code:
    :return:
    """
    return f"/share/download?key={await get_select_token(code)}&code={code}"


async def max_save_times_desc(max_save_seconds: int):
    """
    获取最大保存时间的描述
    :param max_save_seconds:
    :return:
    """

    def gen_desc_zh(value: int, desc: str):
        if value > 0:
            return f"{value}{desc}"
        else:
            return ""

    def gen_desc_en(value: int, desc: str):
        if value > 0:
            ret = f"{value} {desc}"
            if value > 1:
                ret += "s"
            ret += " "
            return ret
        else:
            return ""

    max_timedelta = datetime.timedelta(seconds=max_save_seconds)
    desc_zh, desc_en = "最长保存时间：", "Max save time: "
    desc_zh += gen_desc_zh(max_timedelta.days, "天")
    desc_en += gen_desc_en(max_timedelta.days, "day")
    desc_zh += gen_desc_zh(max_timedelta.seconds // 3600, "小时")
    desc_en += gen_desc_en(max_timedelta.seconds // 3600, "hour")
    desc_zh += gen_desc_zh(max_timedelta.seconds % 3600 // 60, "分钟")
    desc_en += gen_desc_en(max_timedelta.seconds % 3600 // 60, "minute")
    desc_zh += gen_desc_zh(max_timedelta.seconds % 60, "秒")
    desc_en += gen_desc_en(max_timedelta.seconds % 60, "second")
    return desc_zh, desc_en


# scrypt work factors (OWASP-recommended memory-hard parameters; ~50ms/verify)
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
_SCRYPT_MAXMEM = 64 * 1024 * 1024  # hashlib default cap (32MB) is too low for n=2^14,r=8

PASSWORD_SCHEME = "scrypt"  # current scheme for new hashes; sha256/plaintext stay verifiable


def hash_password(password: str) -> str:
    """
    使用 scrypt（memory-hard）哈希密码
    返回格式: scrypt$<n>$<r>$<p>$<salt>$<hash>
    """
    salt = os.urandom(16).hex()
    password_hash = hashlib.scrypt(
        password.encode(),
        salt=salt.encode(),
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=_SCRYPT_MAXMEM,
    ).hex()
    return f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}${salt}${password_hash}"


def verify_password(password: str, hashed: str) -> bool:
    """
    验证密码是否匹配
    支持格式: scrypt$n$r$p$salt$hash（现行）、sha256$salt$hash（历史）、明文（最老）
    """
    if not hashed:
        return False

    if hashed.startswith("scrypt$"):
        parts = hashed.split("$")
        if len(parts) != 6:
            return False
        try:
            scheme, n, r, p, salt, stored_hash = parts
            password_hash = hashlib.scrypt(
                password.encode(),
                salt=salt.encode(),
                n=int(n),
                r=int(r),
                p=int(p),
                maxmem=_SCRYPT_MAXMEM,
            ).hex()
        # 默认解释器对超范围的 n/r/p 抛 TypeError/ValueError；部分构建会抛
        # OverflowError，一并视为校验失败，避免坏掉的存量哈希影响登录路径。
        except (ValueError, TypeError, OverflowError):
            return False
        return hmac.compare_digest(password_hash, stored_hash)

    # sha256 格式: sha256$salt$hash（历史数据，验证逻辑保持原样）
    if hashed.startswith("sha256$"):
        parts = hashed.split("$")
        if len(parts) != 3:
            return False
        _, salt, stored_hash = parts
        password_hash = hashlib.sha256(f"{salt}{password}".encode()).hexdigest()
        return hmac.compare_digest(password_hash, stored_hash)

    # 旧格式: 明文比较 (兼容迁移前的数据)
    return hmac.compare_digest(str(password), str(hashed))


def is_password_hashed(password: str) -> bool:
    """
    检查密码是否已经是哈希格式（现行或历史哈希均视为已哈希）
    """
    if password.startswith("scrypt$") and len(password.split("$")) == 6:
        return True
    return password.startswith("sha256$") and len(password.split("$")) == 3


def password_needs_rehash(hashed: str) -> bool:
    """True when the stored hash uses a legacy scheme (sha256/plaintext)."""
    return bool(hashed) and not hashed.startswith(f"{PASSWORD_SCHEME}$")


async def sanitize_filename(filename: str) -> str:
    """
    安全处理文件名：
    1. 剥离路径只保留文件名
    2. 替换非法字符
    3. 处理空文件名情况
    """
    filename = os.path.basename(filename)
    illegal_chars = r'[\\/*?:"<>|\x00-\x1F]'  # 包含控制字符
    # 替换非法字符为下划线
    cleaned = re.sub(illegal_chars, "_", filename)
    # 处理空格（可选替换为_）
    cleaned = cleaned.replace(" ", "_")
    # 处理连续下划线
    cleaned = re.sub(r"_+", "_", cleaned)
    # 处理首尾特殊字符
    cleaned = cleaned.strip("._")
    # 处理空文件名情况
    if not cleaned:
        cleaned = "unnamed_file"
    # 长度限制（按需调整）
    return cleaned[:255]
