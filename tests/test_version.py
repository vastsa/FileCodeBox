import json
import os
import unittest
from unittest.mock import patch

from core.version import APP_VERSION, VERSION_FILE, load_app_version
from main import app


class ApplicationVersionTests(unittest.TestCase):
    def test_version_file_is_the_runtime_version_source(self):
        version = VERSION_FILE.read_text(encoding="utf-8").strip()

        self.assertRegex(version, r"^\d+\.\d+\.\d+$")
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_app_version(), version)
        self.assertEqual(app.version, APP_VERSION)

    def test_release_manifest_matches_version_file(self):
        manifest_file = VERSION_FILE.parent / ".release-please-manifest.json"
        manifest = json.loads(manifest_file.read_text(encoding="utf-8"))

        self.assertEqual(manifest["."], VERSION_FILE.read_text(encoding="utf-8").strip())

    def test_build_can_override_version_with_environment(self):
        for version in ("9.8.7", "9.8.7-dev+abc123"):
            with self.subTest(version=version):
                with patch.dict(os.environ, {"APP_VERSION": version}):
                    self.assertEqual(load_app_version(), version)

    def test_rejects_non_canonical_versions(self):
        for version in ("v2.4.0", "2.4", "2.4.0 beta"):
            with self.subTest(version=version):
                with patch.dict(os.environ, {"APP_VERSION": version}):
                    with self.assertRaises(RuntimeError):
                        load_app_version()


if __name__ == "__main__":
    unittest.main()
