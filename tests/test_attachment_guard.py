"""Guard: every storage backend forces Content-Disposition: attachment.

The attachment header is the defense that neutralizes stored XSS for
HTML/SVG payloads on the same-origin download path. Regression net for the
five get_file_response implementations — if a backend stops going through
build_attachment_headers (or hand-rolls an inline disposition), the suite
fails here.
"""
import ast
from pathlib import Path

import pytest

from core.storage import build_attachment_headers

BACKEND_MODULES = ("local", "s3", "onedrive", "opendal", "webdav")
SOURCE_DIR = Path("core/storage")


def test_helper_forces_attachment_and_encodes_filename():
    headers = build_attachment_headers("x.html")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert "x.html" in headers["Content-Disposition"]


def test_helper_includes_content_length_when_known():
    headers = build_attachment_headers("x.bin", 123)
    assert headers["Content-Length"] == "123"
    assert "Content-Length" not in build_attachment_headers("x.bin")


def test_every_get_file_response_uses_shared_builder():
    sources = {
        name: (SOURCE_DIR / f"{name}.py").read_text(encoding="utf-8")
        for name in BACKEND_MODULES
    }
    trees = {name: ast.parse(src) for name, src in sources.items()}
    concrete = []
    for mod_name, tree in trees.items():
        for node in ast.walk(tree):
            if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_file_response":
                segment = ast.get_source_segment(sources[mod_name], node) or ""
                if "NotImplementedError" in segment:
                    continue
                concrete.append((mod_name, node, segment))
    assert len(concrete) == 5, "expected one get_file_response per storage backend"
    for mod_name, node, segment in concrete:
        assert "build_attachment_headers(" in segment, (
            f"{mod_name}.get_file_response bypasses the shared attachment "
            "header builder"
        )


@pytest.mark.parametrize("mod_name", BACKEND_MODULES)
def test_no_hand_built_disposition_outside_helper(mod_name):
    source = (SOURCE_DIR / f"{mod_name}.py").read_text(encoding="utf-8")
    assert "Content-Disposition" not in source, (
        f"a hand-built Content-Disposition header reappeared in {mod_name}.py"
    )
