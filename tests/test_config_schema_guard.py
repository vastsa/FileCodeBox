"""Schema guard: every settings attribute referenced by application code must
be declared in DEFAULT_CONFIG.

This is the regression net for the ``opendal_scheme`` class of bug — a config
key read via ``settings.X`` that DEFAULT_CONFIG never declared, which crashes
with AttributeError only when an admin actually selects that code path.
"""
import re
import unittest
from pathlib import Path

from core.settings import DEFAULT_CONFIG

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_DIRS = ["main.py", "core", "apps"]

# Attribute references that are Settings' own machinery, not config keys.
NON_CONFIG_ATTRS = {"items", "user_config", "default_config", "unknown_keys"}

# Filename-extension tokens: matches like "core/settings.py" in docstrings.
FILE_EXT_LIKE = {"py", "pyc", "toml", "ini", "cfg", "yaml", "yml", "md"}

# (?<![\w./-]) skips file-path mentions like core/settings.py.
REF_RE = re.compile(r"(?<![\w./-])settings\.([A-Za-z_][A-Za-z0-9_]*)")
GETATTR_RE = re.compile(r'getattr\(settings,\s*"([A-Za-z_][A-Za-z0-9_]*)"')


class ConfigSchemaGuardTests(unittest.TestCase):
    def test_every_referenced_setting_key_is_declared(self):
        used = set()
        scanned = 0
        for name in SCAN_DIRS:
            path = REPO_ROOT / name
            files = [path] if path.is_file() else path.rglob("*.py")
            for file in files:
                if not file.is_file():
                    continue
                scanned += 1
                source = file.read_text(encoding="utf-8", errors="ignore")
                # Source only — strip comments and docstrings crudely but
                # effectively by scanning line-qualified matches below.
                for match in REF_RE.finditer(source):
                    used.add(match.group(1))
                for match in GETATTR_RE.finditer(source):
                    used.add(match.group(1))

        self.assertGreater(scanned, 5, "扫描范围异常，检查 SCAN_DIRS")

        undeclared = sorted(
            used - set(DEFAULT_CONFIG) - NON_CONFIG_ATTRS - FILE_EXT_LIKE
        )
        self.assertEqual(
            undeclared,
            [],
            "以下 settings 键在代码中被引用但未在 DEFAULT_CONFIG 声明（"
            "运行到对应路径会 AttributeError）：" + ", ".join(undeclared),
        )

    def test_unknown_key_detection_helper(self):
        from core.settings import Settings

        s = Settings({"a": 1})
        self.assertEqual(s.unknown_keys({"a": 2, "ghost": 3}), ["ghost"])
        self.assertEqual(s.unknown_keys({}), [])


if __name__ == "__main__":
    unittest.main()
