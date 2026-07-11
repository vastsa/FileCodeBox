import asyncio
import copy
import unittest

import apps.admin.services as admin_services
import apps.admin.views as admin_views
import apps.admin.dependencies as admin_dependencies
import core.config as core_config
from apps.admin.dependencies import create_token, verify_token
from apps.admin.schemas import LoginData
from apps.admin.services import ConfigService
from fastapi import HTTPException
from main import parse_setup_options
from core.security import (
    LEGACY_DEFAULT_ADMIN_TOKEN,
    is_config_initialized,
    prepare_security_config,
)
from core.settings import DEFAULT_CONFIG, settings
from core.utils import hash_password, verify_password


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


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
                "uploadCount": "30",
                "uploadMinute": "2",
                "errorCount": "5",
                "errorMinute": "1",
                "openUpload": ["0", "1"],
                "enableChunk": "0",
                "code_generate_type": "secret",
                "expireStyle": ["day", "count"],
                "allowed_file_types": ".zip, image/*",
            }
        )

        self.assertEqual(options["uploadSize"], 20 * 1024 * 1024)
        self.assertEqual(options["max_save_seconds"], 7 * 86400)
        self.assertEqual(options["uploadCount"], 30)
        self.assertEqual(options["uploadMinute"], 2)
        self.assertEqual(options["errorCount"], 5)
        self.assertEqual(options["errorMinute"], 1)
        self.assertEqual(options["openUpload"], 1)
        self.assertEqual(options["enableChunk"], 0)
        self.assertEqual(options["code_generate_type"], "secret")
        self.assertEqual(options["expireStyle"], ["day", "count"])
        self.assertEqual(options["allowed_file_types"], [".zip", "image/*"])

    def test_parse_setup_options_allows_turning_guest_upload_off(self):
        options = parse_setup_options(
            {
                "openUpload": "0",
                "expireStyle": ["day"],
            }
        )

        self.assertEqual(options["openUpload"], 0)

    def test_parse_setup_options_requires_expire_style(self):
        with self.assertRaises(ValueError):
            parse_setup_options({"expireStyle": []})


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
        settings.adminSessionExpire = 90 * 24 * 60 * 60
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


async def fake_refresh_settings():
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
            asyncio.run(ConfigService().update_config({"storageLimit": -1}))
        self.assertEqual(context.exception.status_code, 400)

    def test_admin_session_lifetime_rejects_out_of_range_values(self):
        settings.user_config = copy.deepcopy(DEFAULT_CONFIG)

        for invalid_value in (0, 86399, 90000, 365 * 24 * 60 * 60 + 1):
            with self.subTest(invalid_value=invalid_value):
                with self.assertRaises(HTTPException) as context:
                    asyncio.run(
                        ConfigService().update_config(
                            {"adminSessionExpire": invalid_value}
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
                        "uploadSize": 50 * 1024 * 1024,
                        "errorCount": 6,
                        "expireStyle": ["day", "count"],
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
        self.assertEqual(FakeConfigKeyValue.saved_value["uploadSize"], 50 * 1024 * 1024)
        self.assertEqual(FakeConfigKeyValue.saved_value["errorCount"], 6)
        self.assertEqual(FakeConfigKeyValue.saved_value["expireStyle"], ["day", "count"])
