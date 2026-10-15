"""HTTPS works on a Python whose system trust store is empty (python.org macOS installer)."""
import ssl

from alphaspec import client


def test_empty_system_store_falls_back_to_certifi(monkeypatch):
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SSL_CERT_DIR", raising=False)
    real = ssl.create_default_context

    def empty_store(*a, **k):
        ctx = real(*a, **k)
        monkeypatch.setattr(ctx, "cert_store_stats", lambda: {"x509_ca": 0}, raising=False)
        return ctx

    loaded = []
    monkeypatch.setattr(ssl, "create_default_context", empty_store)
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", lambda self, cafile=None, **k: loaded.append(cafile))
    client._ssl_context()
    assert loaded and loaded[0].endswith(".pem")


def test_explicit_cert_file_is_respected(monkeypatch):
    monkeypatch.setenv("SSL_CERT_FILE", "/etc/ssl/cert.pem")
    loaded = []
    monkeypatch.setattr(ssl.SSLContext, "load_verify_locations", lambda self, cafile=None, **k: loaded.append(cafile))
    client._ssl_context()
    assert loaded == []
