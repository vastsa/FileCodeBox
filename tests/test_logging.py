import importlib
import logging
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import core.logger as logger_module


class LoggingConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.environment_patch = None

    def tearDown(self):
        if self.environment_patch is not None:
            self.environment_patch.stop()
        importlib.reload(logger_module)

    def reload_with_environment(self, values):
        self.environment_patch = patch.dict(os.environ, values, clear=True)
        self.environment_patch.start()
        return importlib.reload(logger_module)

    def test_production_defaults_to_warning_and_disables_access_logs(self):
        module = self.reload_with_environment({"APP_ENV": "production"})

        self.assertEqual(module.get_log_level_name(), "warning")
        self.assertEqual(module.logger.level, logging.WARNING)
        self.assertFalse(module.is_access_log_enabled())

    def test_development_defaults_to_info_and_keeps_access_logs(self):
        module = self.reload_with_environment({"APP_ENV": "development"})

        self.assertEqual(module.get_log_level_name(), "info")
        self.assertEqual(module.logger.level, logging.INFO)
        self.assertTrue(module.is_access_log_enabled())

    def test_explicit_log_and_access_settings_override_environment_defaults(self):
        module = self.reload_with_environment(
            {"APP_ENV": "production", "LOG_LEVEL": "error", "ACCESS_LOG": "true"}
        )

        self.assertEqual(module.get_log_level_name(), "error")
        self.assertEqual(module.logger.level, logging.ERROR)
        self.assertTrue(module.is_access_log_enabled())

    def test_log_file_configuration_is_bounded_in_docker_compose(self):
        compose = Path("docker-compose.yml").read_text(encoding="utf-8")
        dockerfile = Path("Dockerfile").read_text(encoding="utf-8")

        self.assertIn('max-size: "10m"', compose)
        self.assertIn('max-file: "3"', compose)
        self.assertIn('APP_ENV="production"', dockerfile)
        self.assertIn('LOG_LEVEL="warning"', dockerfile)
        self.assertIn("--no-access-log", dockerfile)


if __name__ == "__main__":
    unittest.main()
