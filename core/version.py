import os
import re
from pathlib import Path


VERSION_FILE = Path(__file__).resolve().parents[1] / "VERSION"
VERSION_PATTERN = re.compile(
    r"^\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def load_app_version() -> str:
    version = os.getenv("APP_VERSION") or VERSION_FILE.read_text(encoding="utf-8")
    version = version.strip()
    if not VERSION_PATTERN.fullmatch(version):
        raise RuntimeError(f"无效的应用版本号: {version!r}")
    return version


APP_VERSION = load_app_version()
