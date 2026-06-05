import unittest

from core.settings import settings
from core.storage import S3FileStorage


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class S3StorageConfigTests(SettingsOverrideMixin, unittest.TestCase):
    def test_client_config_uses_path_style_when_configured(self):
        storage = S3FileStorage.__new__(S3FileStorage)
        storage.signature_version = "s3v4"
        storage.addressing_style = "path"

        config = storage._client_config()

        self.assertEqual(config.signature_version, "s3v4")
        self.assertEqual(config.s3["addressing_style"], "path")

    def test_client_config_ignores_invalid_addressing_style(self):
        storage = S3FileStorage.__new__(S3FileStorage)
        storage.signature_version = "s3v4"
        storage.addressing_style = "invalid"

        config = storage._client_config()

        self.assertIsNone(config.s3)
