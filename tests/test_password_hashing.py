"""Tests for the scrypt password-hashing scheme and transparent rehash.

Legacy formats (sha256$salt$hash and plaintext) must keep verifying; new
hashes are scrypt (memory-hard). A successful login with a legacy-stored
password upgrades the stored hash in place.
"""
import asyncio
import time
import hashlib
import unittest

from tests.helpers import SettingsOverrideMixin, close_db, init_memory_db

from apps.admin import views as admin_views
from apps.base.models import KeyValue
from core.settings import settings
from core.utils import (
    hash_password,
    is_password_hashed,
    password_needs_rehash,
    verify_password,
)


class PasswordHashSchemeTests(unittest.TestCase):
    def test_scrypt_roundtrip_and_rejection(self):
        hashed = hash_password("s3cret-pass")
        self.assertTrue(hashed.startswith("scrypt$"))
        self.assertTrue(verify_password("s3cret-pass", hashed))
        self.assertFalse(verify_password("wrong-pass", hashed))

    def test_legacy_sha256_and_plaintext_still_verify(self):
        salt = "abcd1234"
        sha_hash = f"sha256${salt}${hashlib.sha256(f'{salt}legacy'.encode()).hexdigest()}"
        self.assertTrue(verify_password("legacy", sha_hash))
        self.assertFalse(verify_password("other", sha_hash))
        self.assertTrue(verify_password("plain", "plain"))
        self.assertFalse(verify_password("plain", "other-plain"))

    def test_scheme_detection_helpers(self):
        scrypt_hash = hash_password("x")
        sha_hash = "sha256$a$b"
        self.assertTrue(is_password_hashed(scrypt_hash))
        self.assertTrue(is_password_hashed(sha_hash))
        self.assertFalse(is_password_hashed("plaintext"))
        self.assertFalse(password_needs_rehash(scrypt_hash))
        self.assertTrue(password_needs_rehash(sha_hash))
        self.assertTrue(password_needs_rehash("plaintext"))
        self.assertFalse(password_needs_rehash(""))

    def test_malformed_hashes_are_rejected_not_crashing(self):
        self.assertFalse(verify_password("x", "scrypt$1$2$3"))
        self.assertFalse(verify_password("x", "scrypt$n$r$p$salt$zzz"))
        self.assertFalse(verify_password("x", "sha256$only-two"))
        self.assertFalse(verify_password("x", ""))
        # 超范围的 n/r/p：解释器抛 TypeError/ValueError（部分构建抛 OverflowError），
        # 都必须被吞掉并判为不匹配，而不是让登录及每个请求 500
        self.assertFalse(
            verify_password("x", "scrypt$99999999999999999999999999$8$1$aa$bb")
        )


class TransparentRehashTests(SettingsOverrideMixin, unittest.TestCase):
    def test_legacy_hash_upgraded_on_successful_login(self):
        asyncio.run(self._scenario())

    async def _scenario(self):
        await init_memory_db()
        try:
            legacy_password = "old-style-pass"
            salt = "feed1234"
            legacy_hash = (
                f"sha256${salt}${hashlib.sha256(f'{salt}{legacy_password}'.encode()).hexdigest()}"
            )
            record = await KeyValue.create(
                key="settings",
                value={"admin_token": legacy_hash, "jwt_secret": "s" * 48},
            )
            settings.user_config = dict(record.value)

            ok = await admin_views.login(
                type("D", (), {"password": legacy_password})(), ip="1.2.3.4"
            )
            self.assertEqual(ok.detail["username"], "admin")

            upgraded = (await KeyValue.filter(key="settings").first()).value["admin_token"]
            self.assertTrue(upgraded.startswith("scrypt$"), upgraded[:20])
            self.assertTrue(verify_password(legacy_password, upgraded))
            self.assertFalse(password_needs_rehash(upgraded))
        finally:
            await close_db()


if __name__ == "__main__":
    unittest.main()


class CheapInitProbeTests(unittest.TestCase):
    """D1 回归：is_config_initialized 在每个请求都会被中间件调用，
    对 scrypt 口令绝不允许跑慢哈希。"""

    def test_scrypt_token_is_initialized_without_slow_hash(self):
        from core.security import is_config_initialized
        from core.utils import hash_password as hp

        token = hp("some-real-password")
        t0 = time.perf_counter()
        self.assertTrue(is_config_initialized({"admin_token": token}))
        self.assertLess(time.perf_counter() - t0, 0.01, "初始化探测不应执行 scrypt")

    def test_empty_and_legacy_default_are_not_initialized(self):
        from core.security import is_config_initialized, LEGACY_DEFAULT_ADMIN_TOKEN

        self.assertFalse(is_config_initialized({"admin_token": ""}))
        self.assertFalse(is_config_initialized({"admin_token": LEGACY_DEFAULT_ADMIN_TOKEN}))


class ConfigCacheTests(unittest.TestCase):
    """D6 回归：TTL 内的 refresh_settings 不再读库，写路径 force=True 必须穿透。

    验证手法（无 mock）：直接改 DB 里的值——
    - TTL 内普通 refresh 不读库 → settings 仍是旧值；
    - force=True 读库 → 新值生效。
    """

    def test_ttl_cache_skips_db_and_force_bypasses(self):
        import apps.base.config as config_module
        from apps.base.models import KeyValue
        from tests.helpers import close_db, init_memory_db

        async def scenario():
            await init_memory_db()
            try:
                row = await KeyValue.create(
                    key="settings", value={"name": "旧值", "admin_token": "x" * 64}
                )
                await config_module.refresh_settings(force=True)
                self.assertEqual(settings.name, "旧值")

                # 直接改 DB（绕过应用层），TTL 内普通 refresh 不应看到
                row.value = {"name": "新值", "admin_token": "x" * 64}
                await row.save()
                await config_module.refresh_settings()
                self.assertEqual(settings.name, "旧值", "TTL 内不应读库")

                await config_module.refresh_settings(force=True)
                self.assertEqual(settings.name, "新值", "force 必须穿透缓存")
            finally:
                config_module._config_cached_until = 0.0
                await close_db()

        asyncio.run(scenario())
