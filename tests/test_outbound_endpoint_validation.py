"""Outbound endpoint SSRF validation (write-entry only).

s3_endpoint_url / s3_hostname / webdav_url are fetched server-side; a
hijacked admin session must not be able to point them at loopback/private
targets. Enforcement applies only with APP_ENV=production so local
development (minio, dev webdav) keeps working; already-stored values are
never re-validated.
"""
import pytest

from core.security import validate_outbound_endpoint, validate_outbound_hostname


@pytest.fixture
def production_env(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://127.0.0.1:9000",
        "https://10.0.0.5",
        "https://192.168.1.10:9000",
        "http://172.16.0.1",
        "http://169.254.169.254/latest/meta-data",
        "https://localhost:9000",
        "https://minio.internal:9000",
        "https://nas.local",
        "file:///etc/passwd",
        "gopher://10.0.0.1",
        "ftp://example.com",
        "not a url",
    ],
)
def test_production_rejects_internal_and_bad_scheme_endpoints(production_env, endpoint):
    with pytest.raises(ValueError):
        validate_outbound_endpoint(endpoint)


@pytest.mark.parametrize(
    "endpoint",
    [
        "",
        "https://s3.amazonaws.com",
        "https://s3.cn-north-1.amazonaws.com.cn",
        "http://example.com:9000",
    ],
)
def test_production_allows_public_https_endpoints(production_env, endpoint):
    assert validate_outbound_endpoint(endpoint) == endpoint


def test_development_env_allows_local_endpoints(monkeypatch):
    monkeypatch.setenv("APP_ENV", "development")
    assert (
        validate_outbound_endpoint("http://127.0.0.1:9000") == "http://127.0.0.1:9000"
    )


@pytest.mark.parametrize(
    "hostname",
    [
        "127.0.0.1",
        "10.0.0.5",
        "192.168.1.10:9000",
        "localhost",
        "minio.internal",
        "nas.local",
    ],
)
def test_production_rejects_internal_hostnames(production_env, hostname):
    with pytest.raises(ValueError):
        validate_outbound_hostname(hostname)


@pytest.mark.parametrize(
    "hostname",
    ["", "s3.amazonaws.com", "minio.corp.example.com", "files.example.com:9000"],
)
def test_production_allows_public_hostnames(production_env, hostname):
    assert validate_outbound_hostname(hostname) == hostname


def test_hostname_tier_rejects_url_forms(production_env):
    """s3_hostname 是裸主机名字段——传 URL 形态直接拒绝（曾用 URL 校验错误处理它）。"""
    with pytest.raises(ValueError):
        validate_outbound_hostname("https://s3.amazonaws.com")
    with pytest.raises(ValueError):
        validate_outbound_hostname("http://127.0.0.1:9000")
