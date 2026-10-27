"""Storage package lazy-loading and instance-reuse contracts.

Importing the app must not drag in the heavy aioboto3/botocore/aiohttp
stack in local-storage deployments, and backends that opt into
``cache_signature()`` must be reused across requests until their
configuration changes.

These run in a subprocess where needed because pytest itself (and other
tests) may already have imported the heavy modules into ``sys.modules``.
"""
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

import core.storage as storage_pkg

ROOT = Path(__file__).resolve().parents[1]
HEAVY_MODULES = ("aioboto3", "botocore", "aiohttp", "office365", "msal", "opendal")


def _run_python(code: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        dict.fromkeys([str(ROOT)] + [p for p in sys.path if p])
    )
    return subprocess.run(
        [sys.executable, "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def test_importing_app_does_not_load_heavy_backends():
    code = (
        "import sys\n"
        "import main\n"
        f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]\n"
        "assert not heavy, heavy\n"
        "print('ok')\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_importing_package_defers_backend_modules():
    code = (
        "import sys\n"
        "import core.storage\n"
        "assert 'core.storage.s3' not in sys.modules\n"
        "assert 'core.storage.local' not in sys.modules\n"
        f"heavy = [m for m in {HEAVY_MODULES!r} if m in sys.modules]\n"
        "assert not heavy, heavy\n"
        "from core.storage import S3FileStorage\n"
        "assert 'core.storage.s3' in sys.modules\n"
        "assert 'aioboto3' in sys.modules\n"
        "print('ok')\n"
    )
    result = _run_python(code)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


def test_registry_has_all_historical_backends():
    assert set(storage_pkg.storages) == {
        "local",
        "s3",
        "onedrive",
        "opendal",
        "webdav",
    }


def test_unknown_lazy_export_raises_attribute_error():
    with pytest.raises(AttributeError):
        getattr(storage_pkg, "NoSuchStorage")


def test_local_backend_is_not_reused():
    """local 构造极轻，且测试/运行时会 patch data_root——必须每次新实例。"""
    factory = storage_pkg.storages["local"]
    assert factory() is not factory()


def test_factory_reuses_instance_until_config_changes(monkeypatch):
    import core.storage.s3 as s3_module
    from core.settings import settings

    created = []

    class FakeS3:
        def __init__(self):
            created.append(self)

        @classmethod
        def cache_signature(cls):
            return (repr(getattr(settings, "s3_endpoint_url", None)),)

    monkeypatch.setattr(s3_module, "S3FileStorage", FakeS3)
    factory = storage_pkg.storages["s3"]
    monkeypatch.setattr(factory, "_cached", None)

    first = factory()
    second = factory()
    assert first is second
    assert len(created) == 1

    monkeypatch.setattr(settings, "s3_endpoint_url", "https://changed.example")
    third = factory()
    assert third is not first
    assert len(created) == 2


def test_patch_dict_still_intercepts_registry():
    """历史测试通过 patch.dict(views.storages, {...}) 注入 FakeStorage。"""

    class FakeStorage:
        pass

    with patch.dict(storage_pkg.storages, {"local": FakeStorage}):
        assert isinstance(storage_pkg.storages["local"](), FakeStorage)

    assert not isinstance(storage_pkg.storages["local"](), FakeStorage)
