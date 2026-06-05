import asyncio
import unittest

from fastapi import HTTPException

from core.settings import settings
from main import index, resolve_theme_file


class SettingsOverrideMixin:
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config


class ThemeAssetTests(SettingsOverrideMixin, unittest.TestCase):
    def test_resolves_assets_from_current_theme(self):
        settings.themesSelect = "themes/2023"
        theme_2023_asset = resolve_theme_file("assets", "index-CxMsK_Ni.js")

        settings.themesSelect = "themes/2024"
        theme_2024_asset = resolve_theme_file("assets", "index-DjzJA_Oj.js")

        self.assertIn("themes/2023/assets", str(theme_2023_asset))
        self.assertIn("themes/2024/assets", str(theme_2024_asset))

    def test_rejects_theme_asset_path_traversal(self):
        settings.themesSelect = "themes/2024"

        with self.assertRaises(HTTPException) as error:
            resolve_theme_file("assets", "..", "..", "core", "settings.py")

        self.assertEqual(error.exception.status_code, 404)

    def test_index_keeps_absolute_asset_urls(self):
        settings.themesSelect = "themes/2023"

        response = asyncio.run(index())
        html = response.body.decode("utf-8")

        self.assertIn('src="/assets/', html)
        self.assertIn('href="/assets/', html)
