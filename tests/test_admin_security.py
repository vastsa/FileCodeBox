import asyncio
import copy
import unittest

import apps.admin.services as admin_services
import apps.admin.views as admin_views
import apps.admin.dependencies as admin_dependencies
import apps.base.config as core_config
from apps.admin.dependencies import create_token, verify_token
from apps.admin.schemas import LoginData
from apps.admin.services import ConfigService
from fastapi import HTTPException
from apps.base.setup_wizard import parse_setup_options
from core.security import (
    LEGACY_DEFAULT_ADMIN_TOKEN,
    is_config_initialized,
    prepare_security_config,
)
from core.settings import DEFAULT_CONFIG, settings
from core.utils import hash_password, verify_password


from tests.helpers import SettingsOverrideMixin


class SecurityConfigTests(unittest.TestCase):
    def test_initial_security_config_requires_setup_and_generates_jwt_secret(self):
        result = prepare_security_config(DEFAULT_CONFIG)

        self.assertTrue(result.changed)
        self.assertTrue(result.setup_required)
        self.assertEqual(result.config["admin_token"], "")
        self.assertFalse(is_config_initialized(result.config))
        self.assertGreaterEqual(len(result.config["jwt_secret"]), 32)

    def test_legacy_default_password_requires_setup(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["admin_token"] = hash_password(LEGACY_DEFAULT_ADMIN_TOKEN)
        config["jwt_secret"] = "j" * 48

        result = prepare_security_config(config)

        self.assertTrue(result.setup_required)
        self.assertEqual(result.config["admin_token"], "")
        self.assertEqual(result.config["jwt_secret"], "j" * 48)

    def test_custom_plaintext_password_is_hashed_and_initialized(self):
        config = copy.deepcopy(DEFAULT_CONFIG)
        config["admin_token"] = "custom-password"
        config["jwt_secret"] = "j" * 48

        result = prepare_security_config(config)

        self.assertTrue(result.password_hashed)
        self.assertTrue(is_config_initialized(result.config))
        self.assertTrue(verify_password("custom-password", result.config["admin_token"]))


class SetupOptionTests(unittest.TestCase):
    def test_parse_setup_options_converts_common_fields(self):
        options = parse_setup_options(
            {
                "upload_size_value": "20",
                "upload_size_unit": "MB",
                "save_time_value": "7",
                "save_time_unit": "day",
                "upload_count": "30",
                "upload_minute": "2",
                "error_count": "5",
                "error_minute": "1",
                "login_count": "4",
                "login_minute": "20",
                "open_upload": ["0", "1"],
                "enable_chunk": "0",
                "code_generate_type": "secret",
                "expire_style": ["day", "count"],
                "allowed_file_types": ".zip, image/*",
            }
        )

        self.assertEqual(options["upload_size"], 20 * 1024 * 1024)
        self.assertEqual(options["max_save_seconds"], 7 * 86400)
        self.assertEqual(options["upload_count"], 30)
        self.assertEqual(options["upload_minute"], 2)
        self.assertEqual(options["error_count"], 5)
        self.assertEqual(options["error_minute"], 1)
        self.assertEqual(options["login_count"], 4)
        self.assertEqual(options["login_minute"], 20)
        self.assertEqual(options["open_upload"], 1)
        self.assertEqual(options["enable_chunk"], 0)
        self.assertEqual(options["code_generate_type"], "secret")
        self.assertEqual(options["expire_style"], ["day", "count"])
        self.assertEqual(options["allowed_file_types"], [".zip", "image/*"])

    def test_parse_setup_options_allows_turning_guest_upload_off(self):
        options = parse_setup_options(
            {
                "open_upload": "0",
                "expire_style": ["day"],
            }
        )

        self.assertEqual(options["open_upload"], 0)

    def test_parse_setup_options_requires_expire_style(self):
        with self.assertRaises(ValueError):
            parse_setup_options({"expire_style": []})


class AdminJwtTests(SettingsOverrideMixin, unittest.TestCase):
    def test_admin_jwt_signature_uses_independent_secret(self):
        settings.admin_token = hash_password("old-admin-password")
        settings.jwt_secret = "j" * 48

        token = create_token({"is_admin": True}, expires_in=60)
        self.assertTrue(verify_token(token)["is_admin"])

        settings.admin_token = hash_password("new-admin-password")
        self.assertTrue(verify_token(token)["is_admin"])

        settings.jwt_secret = "k" * 48
        with self.assertRaises(ValueError):
            verify_token(token)

    def test_configured_session_lifetime_is_returned_by_login(self):
        settings.admin_token = hash_password("admin-password")
        settings.jwt_secret = "j" * 48
        settings.admin_session_expire = 90 * 24 * 60 * 60
        original_time = admin_dependencies.time.time
        admin_dependencies.time.time = lambda: 1_800_000_000
        try:
            response = asyncio.run(
                admin_views.login(LoginData(password="admin-password"))
            )
            payload = verify_token(response.detail["token"])
        finally:
            admin_dependencies.time.time = original_time

        self.assertEqual(response.detail["expires_in"], 90 * 24 * 60 * 60)
        self.assertEqual(
            response.detail["expires_at"], 1_800_000_000 + 90 * 24 * 60 * 60
        )
        self.assertEqual(payload["exp"], response.detail["expires_at"])


class FakeKeyValue:
    saved_value = None

    @classmethod
    async def update_or_create(cls, key, defaults):
        cls.saved_value = defaults["value"]
        return None, True


async def fake_refresh_settings(force=False):
    return None


class FakeConfigRecord:
    def __init__(self, value):
        self.value = value


class FakeConfigQuery:
    async def first(self):
        return FakeConfigKeyValue.record


class FakeConfigKeyValue:
    record = None
    saved_value = None

    @classmethod
    def filter(cls, key):
        return FakeConfigQuery()

    @classmethod
    async def update_or_create(cls, key, defaults):
        cls.saved_value = defaults["value"]
        return None, True


class ConfigServiceSecurityTests(SettingsOverrideMixin, unittest.TestCase):
    def test_storage_limit_rejects_negative_values(self):
        settings.user_config = copy.deepcopy(DEFAULT_CONFIG)
        with self.assertRaises(HTTPException) as context:
            asyncio.run(ConfigService().update_config({"storage_limit": -1}))
        self.assertEqual(context.exception.status_code, 400)

    def test_admin_session_lifetime_rejects_out_of_range_values(self):
        settings.user_config = copy.deepcopy(DEFAULT_CONFIG)

        for invalid_value in (0, 86399, 90000, 365 * 24 * 60 * 60 + 1):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(HTTPException) as context:
                    asyncio.run(
                        ConfigService().update_config(
                            {"admin_session_expire": invalid_value}
                        )
                    )
                self.assertEqual(context.exception.status_code, 400)

    def test_admin_password_update_rotates_jwt_secret(self):
        old_secret = "j" * 48
        settings.user_config = {
            **copy.deepcopy(DEFAULT_CONFIG),
            "admin_token": hash_password("old-admin-password"),
            "jwt_secret": old_secret,
        }
        original_key_value = admin_services.KeyValue
        original_refresh_settings = admin_services.refresh_settings
        admin_services.KeyValue = FakeKeyValue
        admin_services.refresh_settings = fake_refresh_settings
        FakeKeyValue.saved_value = None
        try:
            asyncio.run(ConfigService().update_config({"admin_token": "new-admin-password"}))
        finally:
            admin_services.KeyValue = original_key_value
            admin_services.refresh_settings = original_refresh_settings

        self.assertIsNotNone(FakeKeyValue.saved_value)
        self.assertTrue(verify_password("new-admin-password", FakeKeyValue.saved_value["admin_token"]))
        self.assertNotEqual(FakeKeyValue.saved_value["jwt_secret"], old_secret)
        self.assertGreaterEqual(len(FakeKeyValue.saved_value["jwt_secret"]), 32)

    def test_initialize_system_sets_admin_password_and_jwt_secret(self):
        original_key_value = core_config.KeyValue
        original_refresh_settings = core_config.refresh_settings
        FakeConfigKeyValue.record = FakeConfigRecord(
            {
                **copy.deepcopy(DEFAULT_CONFIG),
                "admin_token": "",
                "jwt_secret": "",
            }
        )
        FakeConfigKeyValue.saved_value = None
        core_config.KeyValue = FakeConfigKeyValue
        core_config.refresh_settings = fake_refresh_settings
        try:
            asyncio.run(
                core_config.initialize_system(
                    admin_password="new-admin-password",
                    site_name="我的文件快递柜",
                    setup_options={
                        "upload_size": 50 * 1024 * 1024,
                        "error_count": 6,
                        "expire_style": ["day", "count"],
                    },
                )
            )
        finally:
            core_config.KeyValue = original_key_value
            core_config.refresh_settings = original_refresh_settings

        self.assertIsNotNone(FakeConfigKeyValue.saved_value)
        self.assertTrue(
            verify_password("new-admin-password", FakeConfigKeyValue.saved_value["admin_token"])
        )
        self.assertGreaterEqual(len(FakeConfigKeyValue.saved_value["jwt_secret"]), 32)
        self.assertEqual(FakeConfigKeyValue.saved_value["name"], "我的文件快递柜")
        self.assertEqual(FakeConfigKeyValue.saved_value["upload_size"], 50 * 1024 * 1024)
        self.assertEqual(FakeConfigKeyValue.saved_value["error_count"], 6)
        self.assertEqual(FakeConfigKeyValue.saved_value["expire_style"], ["day", "count"])
