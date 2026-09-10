"""Guard: every storage backend forces Content-Disposition: attachment.

The attachment header is the defense that neutralizes stored XSS for
HTML/SVG payloads on the same-origin download path. Regression net for the
five get_file_response implementations — if a backend stops going through
build_attachment_headers (or hand-rolls an inline disposition), the suite
fails here.
"""
import ast
from pathlib import Path

from core.storage import build_attachment_headers


def test_helper_forces_attachment_and_encodes_filename():
    headers = build_attachment_headers("x.html")
    assert headers["Content-Disposition"].startswith("attachment;")
    assert "x.html" in headers["Content-Disposition"]


def test_helper_includes_content_length_when_known():
    headers = build_attachment_headers("x.bin", 123)
    assert headers["Content-Length"] == "123"
    assert "Content-Length" not in build_attachment_headers("x.bin")


def test_every_get_file_response_uses_shared_builder():
    source = Path("core/storage.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    methods = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "get_file_response"
    ]
    concrete = [
        m
        for m in methods
        if "NotImplementedError" not in ast.get_source_segment(source, m)
    ]
    assert len(methods) - len(concrete) == 1, "expected exactly one abstract stub"
    assert len(concrete) == 5, "expected one get_file_response per storage backend"
    for method in concrete:
        segment = ast.get_source_segment(source, method)
        assert segment is not None
        assert "build_attachment_headers(" in segment, (
            f"get_file_response at line {method.lineno} bypasses the shared "
            "attachment header builder"
        )


def test_no_hand_built_disposition_outside_helper():
    source = Path("core/storage.py").read_text(encoding="utf-8")
    helper_start = source.index("def build_attachment_headers")
    helper_end = source.index("class FileStorageInterface")
    outside_helper = source[:helper_start] + source[helper_end:]
    assert "Content-Disposition" not in outside_helper, (
        "a hand-built Content-Disposition header reappeared outside "
        "build_attachment_headers"
    )
