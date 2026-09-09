import copy
import secrets
from dataclasses import dataclass
from typing import Any

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
