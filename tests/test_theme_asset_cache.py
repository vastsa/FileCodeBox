"""Theme assets get a safe Cache-Control policy.

Fingerprinted (Vite) filenames can be cached immutably; public assets whose
names do not change must use a short TTL so in-place upgrades are picked up.
"""
import asyncio
import tempfile
import unittest
from pathlib import Path

import apps.base.pages as pages


class ThemeAssetCacheTests(unittest.TestCase):
    def setUp(self):
        self._original_resolve_theme_file = pages.resolve_theme_file
        self._tmpdir = tempfile.TemporaryDirectory()
        self.root = Path(self._tmpdir.name)
        (self.root / "assets").mkdir()
        pages.resolve_theme_file = lambda *parts: self.root.joinpath(*parts)

    def tearDown(self):
        pages.resolve_theme_file = self._original_resolve_theme_file
        self._tmpdir.cleanup()

    def _asset_response(self, name: str):
        (self.root / "assets" / name).write_bytes(b"x")
        return asyncio.run(pages.theme_asset(name))

    def test_fingerprinted_asset_is_immutable(self):
        response = self._asset_response("index-BX2s1QqP.js")

        self.assertIn("max-age=31536000", response.headers["cache-control"])
        self.assertIn("immutable", response.headers["cache-control"])

    def test_plain_asset_gets_short_cache(self):
        response = self._asset_response("logo.png")

        self.assertIn("max-age=86400", response.headers["cache-control"])
        self.assertNotIn("immutable", response.headers["cache-control"])

    def test_short_hash_is_not_treated_as_fingerprint(self):
        self.assertEqual(
            pages._asset_cache_control("logo-2024.png"),
            pages._DEFAULT_ASSET_CACHE,
        )
        self.assertEqual(
            pages._asset_cache_control("index-BX2s1QqP.css"),
            pages._IMMUTABLE_ASSET_CACHE,
        )


if __name__ == "__main__":
    unittest.main()
