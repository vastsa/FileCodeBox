"""index.html render cache must stay correct across config/theme changes."""
import asyncio
import os
import tempfile
import unittest
from pathlib import Path

from fastapi import HTTPException

import apps.base.pages as pages
from core.settings import settings


class IndexRenderCacheTests(unittest.TestCase):
    def setUp(self):
        self._original_user_config = dict(settings.user_config)
        self._original_resolve_theme_file = pages.resolve_theme_file
        self._tmpdir = tempfile.TemporaryDirectory()
        self.template = Path(self._tmpdir.name) / "index.html"
        self.template.write_text(
            "<title>{{title}}</title>"
            '<meta name="description" content="{{description}}">'
            "<div>{{opacity}}</div>",
            encoding="utf-8",
        )
        pages.resolve_theme_file = lambda *args, **kwargs: self.template
        pages._render_index_html.cache_clear()

    def tearDown(self):
        pages.resolve_theme_file = self._original_resolve_theme_file
        settings.user_config = self._original_user_config
        pages._render_index_html.cache_clear()
        self._tmpdir.cleanup()

    def _render(self) -> str:
        return asyncio.run(pages.index()).body.decode("utf-8")

    def test_repeated_requests_hit_the_render_cache(self):
        first = self._render()
        second = self._render()

        self.assertEqual(first, second)
        info = pages._render_index_html.cache_info()
        self.assertEqual(info.misses, 1)
        self.assertEqual(info.hits, 1)

    def test_site_config_change_invalidates_cache(self):
        self._render()

        settings.name = "New Site Name"
        html = self._render()

        self.assertIn("<title>New Site Name</title>", html)
        self.assertEqual(pages._render_index_html.cache_info().misses, 2)

    def test_template_replacement_invalidates_cache(self):
        self._render()
        old_stat = self.template.stat()

        self.template.write_text(
            "<title>{{title}}</title><p>rebuilt</p>", encoding="utf-8"
        )
        os.utime(
            self.template,
            ns=(old_stat.st_atime_ns, old_stat.st_mtime_ns + 1_000_000),
        )

        html = self._render()
        self.assertIn("<p>rebuilt</p>", html)
        self.assertEqual(pages._render_index_html.cache_info().misses, 2)

    def test_missing_template_still_404s_instead_of_serving_cache(self):
        self._render()
        self.template.unlink()

        with self.assertRaises(HTTPException) as ctx:
            asyncio.run(pages.index())
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
