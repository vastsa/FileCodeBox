"""Issue #531: keep a legacy filename alongside the RFC 5987 UTF-8 name."""
import re
from types import SimpleNamespace
from urllib.parse import quote, unquote

import pytest

from apps.base import local_share, views
from apps.base.models import FileCodes
from core.settings import settings
from core.storage import build_attachment_headers


def legacy_filename(disposition):
    match = re.search(r'(?:^|;\s*)filename="([^"]+)"', disposition)
    assert match is not None, "legacy download clients cannot read filename*"
    return match.group(1)


@pytest.mark.parametrize(
    ("filename", "fallback"),
    [
        ("report.pdf", "report.pdf"),
        ("my archive.tar.gz", "my archive.tar.gz"),
        ("报告.pdf", "__.pdf"),
        ("图像 🖼.png", "__ _.png"),
        ("", "download"),
    ],
)
def test_attachment_has_legacy_and_utf8_filenames(filename, fallback):
    headers = build_attachment_headers(filename, 42)
    disposition = headers["Content-Disposition"]
    assert disposition.startswith("attachment;")
    assert legacy_filename(disposition) == fallback
    assert disposition.endswith("filename*=UTF-8''" + quote(filename, safe=""))
    assert headers["Content-Length"] == "42"
    assert disposition.isascii()


def test_legacy_fallback_cannot_inject_parameters_headers_or_paths():
    filename = '../bad\\name"; inline;\r\nX-Evil: true\x00%20.html'
    disposition = build_attachment_headers(filename)["Content-Disposition"]
    fallback = legacy_filename(disposition)
    assert re.fullmatch(r"[A-Za-z0-9._ -]+", fallback)
    assert not fallback.startswith(".")
    assert fallback.endswith(".html")
    assert "\r" not in disposition and "\n" not in disposition and "\x00" not in disposition
    assert len(disposition.split(";")) == 3
    assert unquote(disposition.split("filename*=UTF-8''", 1)[1]) == filename


def test_local_reference_download_uses_compatible_headers(tmp_path, monkeypatch):
    source = tmp_path / "报告.pdf"
    source.write_bytes(b"pdf contents")
    monkeypatch.setattr(local_share, "get_local_root", lambda: tmp_path)
    record = SimpleNamespace(uuid_file_name=source.name, prefix="报告", suffix=".pdf")

    download = local_share.build_local_ref_download(record)

    assert download.path == source
    assert download.headers == build_attachment_headers("报告.pdf", source.stat().st_size)
    assert legacy_filename(download.headers["Content-Disposition"]) == "__.pdf"


@pytest.mark.asyncio
async def test_text_download_uses_compatible_headers(db, monkeypatch):
    monkeypatch.setattr(settings, "user_config", dict(settings.user_config))
    settings.file_storage = "local"
    record = await FileCodes.create(
        code="legacy-text",
        prefix="文本",
        text="hello, 文本直链",
        expired_count=-1,
        expired_at=None,
    )

    response = await views.get_code_file(code=record.code, ip="127.0.0.1")

    assert response.status_code == 200
    assert response.body.decode("utf-8") == record.text
    assert response.headers["content-disposition"] == build_attachment_headers("文本.txt")[
        "Content-Disposition"
    ]
    assert legacy_filename(response.headers["content-disposition"]) == "__.txt"
