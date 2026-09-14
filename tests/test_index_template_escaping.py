import asyncio
import tempfile
import unittest
from pathlib import Path

import apps.base.pages as pages
from core.settings import settings


class IndexTemplateEscapingTests(unittest.TestCase):
    """Regression: site config must be html.escape-d before template injection
    (stored XSS prevention).

    Uses a temp file as a stand-in for themes/*/index.html so the test also
    runs in a bare checkout without built frontends.
    """

    def setUp(self):
        self._original_user_config = dict(settings.user_config)
        self._original_resolve_theme_file = pages.resolve_theme_file
        tmp = tempfile.NamedTemporaryFile(
            "w", suffix=".html", delete=False, encoding="utf-8"
        )
        tmp.write(
            "<title>{{title}}</title>"
            '<meta name="description" content="{{description}}">'
            "<div>{{opacity}}</div>"
        )
        tmp.close()
        self._template_path = Path(tmp.name)

    def tearDown(self):
        settings.user_config = self._original_user_config
        pages.resolve_theme_file = self._original_resolve_theme_file
        self._template_path.unlink()

    def _patch_template(self):
        pages.resolve_theme_file = lambda *args, **kwargs: self._template_path

    def _render_index_html(self) -> str:
        return asyncio.run(pages.index()).body.decode("utf-8")

    def test_malicious_site_config_is_escaped(self):
        self._patch_template()
        settings.name = "<script>alert(1)</script>"
        settings.description = '"><img src=x onerror=alert(2)>'

        html = self._render_index_html()

        self.assertNotIn("<script>alert", html)
        self.assertNotIn("<img", html)
        self.assertIn("&lt;script&gt;", html)

    def test_plain_site_config_renders_unchanged(self):
        self._patch_template()
        settings.name = "FileCodeBox"
        settings.description = "A simple file share service"
        settings.opacity = 0.9

        html = self._render_index_html()

        self.assertIn("<title>FileCodeBox</title>", html)
        self.assertIn('content="A simple file share service"', html)
        self.assertIn("<div>0.9</div>", html)


if __name__ == "__main__":
    unittest.main()
