import asyncio
import unittest

from fastapi import HTTPException

from core.settings import BASE_DIR, settings
from apps.base.pages import index, resolve_theme_file
from tests.helpers import SettingsOverrideMixin

# themes/ is produced by the Dockerfile frontend build (see .gitignore); the test
# switches between both bundled themes, so it needs both to exist locally.
THEMES_BUILT = all(
    BASE_DIR.joinpath(f"themes/{year}/assets").is_dir() for year in ("2023", "2024")
)


class ThemeAssetTests(SettingsOverrideMixin, unittest.TestCase):
    def get_theme_index_asset(self, theme: str) -> str:
        assets = sorted((BASE_DIR / theme / "assets").glob("index-*.js"))
        self.assertTrue(assets, f"{theme} 缺少 index JS 资源")
        return assets[0].name

    @unittest.skipUnless(THEMES_BUILT, "themes/ exists only after the Docker frontend build; skip in bare checkouts")
    def test_resolves_assets_from_current_theme(self):
        settings.themes_select = "themes/2023"
        theme_2023_asset = resolve_theme_file(
            "assets", self.get_theme_index_asset("themes/2023")
        )

        settings.themes_select = "themes/2024"
        theme_2024_asset = resolve_theme_file(
            "assets", self.get_theme_index_asset("themes/2024")
        )

        self.assertIn("themes/2023/assets", str(theme_2023_asset))
        self.assertIn("themes/2024/assets", str(theme_2024_asset))

    def test_rejects_theme_asset_path_traversal(self):
        settings.themes_select = "themes/2024"

        with self.assertRaises(HTTPException) as error:
            resolve_theme_file("assets", "..", "..", "core", "settings.py")

        self.assertEqual(error.exception.status_code, 404)

    @unittest.skipUnless(THEMES_BUILT, "themes/ exists only after the Docker frontend build; skip in bare checkouts")
    def test_index_keeps_absolute_asset_urls(self):
        settings.themes_select = "themes/2023"

        response = asyncio.run(index())
        html = response.body.decode("utf-8")

        self.assertIn('src="/assets/', html)
        self.assertIn('href="/assets/', html)
