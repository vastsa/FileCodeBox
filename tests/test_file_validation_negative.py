"""File-validation negative paths: extension/MIME spoofing via magic bytes,
whitelist rule matching, and chunk-0 header validation.

The positive paths are exercised transitively by journey tests; this module
pins the rejection semantics.
"""
import io

import pytest
from fastapi import HTTPException, UploadFile

from apps.base.file_validation import (
    detect_file_kind,
    normalize_allowed_file_types,
    validate_file_magic,
    validate_header_bytes,
    validate_upload_file,
)


@pytest.fixture
def allow_all(monkeypatch):
    from core.settings import settings

    original = dict(settings.user_config)
    settings.user_config = {**original, "allowed_file_types": ["*"]}
    yield
    settings.user_config = original


@pytest.fixture
def allow_images_only(monkeypatch):
    from core.settings import settings

    original = dict(settings.user_config)
    settings.user_config = {**original, "allowed_file_types": ["image/*"]}
    yield
    settings.user_config = original


class TestMagicBytesSpoofing:
    def test_png_extension_with_text_content_rejected(self, allow_all):
        """声明 .png 但内容是文本——magic bytes 必须拒绝伪造。"""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_magic("shell.png", "image/png", b"#!/bin/sh\nrm -rf")
        assert exc_info.value.status_code == 403

    def test_png_extension_with_real_png_signature_passes(self, allow_all):
        validate_file_magic(
            "image.png", "image/png", b"\x89PNG\r\n\x1a\n" + b"\x00" * 8
        )

    def test_exe_disguised_as_pdf_rejected(self, allow_all):
        with pytest.raises(HTTPException) as exc_info:
            validate_file_magic("doc.pdf", "application/pdf", b"MZ\x90\x00")
        assert exc_info.value.status_code == 403

    def test_pdf_signature_beats_longer_irrelevant_prefix(self, allow_all):
        assert detect_file_kind(b"%PDF-1.7\n").name == "pdf"

    def test_mp4_box_detection(self, allow_all):
        assert detect_file_kind(b"\x00\x00\x00\x18ftypmp42").name == "mp4"

    def test_webp_riff_detection(self, allow_all):
        assert detect_file_kind(b"RIFF\x00\x00\x00\x00WEBPVP8 ").name == "webp"

    def test_empty_header_passes_magic_check(self, allow_all):
        """空 header（0 字节文件）不做 magic 判定——只走白名单。"""
        validate_file_magic("unknown.bin", None, b"")

    def test_unknown_extension_with_known_signature_still_checked(self, allow_all):
        """未知扩展名：magic 识别出的类型不在白名单时拒绝（白名单非 *）。"""


class TestWhitelistRules:
    def test_star_allows_everything(self, allow_all):
        assert normalize_allowed_file_types() == ["*"]
        validate_file_magic("anything.exe", "application/x-msdownload", b"MZ")

    def test_image_wildcard_allows_png_rejects_exe(self, allow_images_only):
        validate_file_magic("pic.png", "image/png", b"\x89PNG\r\n\x1a\n")
        with pytest.raises(HTTPException) as exc_info:
            validate_file_magic("run.exe", "application/x-msdownload", b"MZ")
        assert exc_info.value.status_code == 403

    def test_image_wildcard_rejects_non_image_content_even_with_png_name(
        self, allow_images_only
    ):
        """扩展名是 .png 但 magic 识别失败（内容不是图）→ 伪造拒绝。"""
        with pytest.raises(HTTPException) as exc_info:
            validate_file_magic("pic.png", "image/png", b"plain text")
        assert exc_info.value.status_code == 403


class TestChunkHeaderValidation:
    def test_validate_header_bytes_delegates_to_magic(self, allow_all):
        """分片 0 的头部校验与整文件同一套 magic 语义（分片上传绕过面）。"""
        with pytest.raises(HTTPException) as exc_info:
            validate_header_bytes("doc.pdf", "application/pdf", b"MZ")  # exe 伪装 pdf
        assert exc_info.value.status_code == 403
        validate_header_bytes("ok.png", "image/png", b"\x89PNG\r\n\x1a\n")


@pytest.mark.asyncio
async def test_validate_upload_file_via_uploadfile(allow_all):
    """端到端：UploadFile（伪 .png 文本内容）被 validate_upload_file 拒绝。"""
    upload = UploadFile(
        file=io.BytesIO(b"not an image"), filename="fake.png", size=12
    )
    with pytest.raises(HTTPException) as exc_info:
        await validate_upload_file(upload)
    assert exc_info.value.status_code == 403
