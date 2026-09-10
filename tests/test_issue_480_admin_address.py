import unittest

from core.settings import settings
from apps.base.pages import build_public_config, build_public_meta


class AdminAddressPublicConfigTests(unittest.TestCase):
    def setUp(self):
        self._original_user_config = dict(settings.user_config)

    def tearDown(self):
        settings.user_config = self._original_user_config

    def test_admin_address_is_exposed_as_strict_binary_flag(self):
        cases = ((0, 0), (1, 1), ("0", 0), ("1", 1))

        for configured_value, expected_value in cases:
            with self.subTest(configured_value=configured_value):
                settings.show_admin_addr = configured_value

                public_value = build_public_config()["show_admin_address"]
                feature_value = build_public_meta()["features"]["admin_address_visible"]

                self.assertIs(type(public_value), int)
                self.assertEqual(public_value, expected_value)
                self.assertIs(feature_value, bool(expected_value))
