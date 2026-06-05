import unittest

from fastapi import HTTPException

from apps.base.views import validate_file_type
from core.settings import settings


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class FileTypeValidationTests(SettingsOverrideMixin, unittest.TestCase):
    def test_allows_extensions_and_mime_patterns(self):
        settings.allowed_file_types = ["rar", ".zip", "image/*"]

        validate_file_type("backup.RAR")
        validate_file_type("archive.zip")
        validate_file_type("avatar.bin", "image/png")

    def test_rejects_disallowed_file_type(self):
        settings.allowed_file_types = ["rar"]

        with self.assertRaises(HTTPException) as error:
            validate_file_type("payload.exe", "application/octet-stream")

        self.assertEqual(error.exception.status_code, 403)
