"""Tests for telnet over TLS (TELNETS) via telnetlib3's ssl/tls_auto support."""
from __future__ import annotations

import asyncio
import socket
import ssl
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import telnetlib3

import atheriz.settings as settings
from atheriz.network.telnet import TelnetProtocol, build_telnet_ssl_context


def _make_self_signed(tmp_path) -> tuple[Path, Path, Path]:
    key = tmp_path / "key.pem"
    cert = tmp_path / "cert.pem"
    try:
        subprocess.run(
            [
                "openssl", "req", "-x509", "-newkey", "rsa:2048",
                "-keyout", str(key), "-out", str(cert),
                "-days", "1", "-nodes", "-subj", "/CN=localhost",
            ],
            check=True, capture_output=True,
        )
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("openssl not available")
    combined = tmp_path / "combined.pem"
    combined.write_text(cert.read_text() + key.read_text())
    return key, cert, combined


class _ServerStub:
    def __init__(self):
        self._closed = False

    def close(self):
        self._closed = True

    async def wait_closed(self):
        return None


async def _fake_create_server(*args, **kwargs):
    return _ServerStub(), kwargs


def _mount(app):
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def original(app):
        yield

    app.router.lifespan_context = original
    TelnetProtocol.setup(app)
    return app.router.lifespan_context


def _run_lifespan(lifespan, app):
    async def run():
        async with lifespan(app):
            pass

    asyncio.run(run())


class TestBuildTelnetSslContext:
    def test_none_when_cert_unset(self, monkeypatch):
        monkeypatch.setattr(settings, "SSL_CERTFILE", None)
        assert build_telnet_ssl_context() is None

    def test_none_when_cert_missing(self, monkeypatch):
        monkeypatch.setattr(settings, "SSL_CERTFILE", "/nonexistent/cert.pem")
        assert build_telnet_ssl_context() is None

    def test_loads_combined_pem(self, monkeypatch, tmp_path):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        context = build_telnet_ssl_context()
        assert context is not None
        assert isinstance(context, ssl.SSLContext)

    def test_loads_separate_key(self, monkeypatch, tmp_path):
        key, cert, _ = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", str(key))
        context = build_telnet_ssl_context()
        assert context is not None

    def test_none_when_key_missing(self, monkeypatch, tmp_path):
        key, cert, _ = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", str(tmp_path / "missing.key"))
        assert build_telnet_ssl_context() is None


class TestTelnetProtocolTLSWiring:
    def test_passes_ssl_and_tls_auto_when_enabled(self, monkeypatch, tmp_path, global_test_env):
        from fastapi import FastAPI
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", True)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _ServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert isinstance(captured.get("ssl"), ssl.SSLContext)
        assert captured.get("tls_auto") is True

    def test_no_ssl_kwargs_when_disabled(self, monkeypatch, tmp_path, global_test_env):
        from fastapi import FastAPI
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", False)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _ServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert "ssl" not in captured
        assert "tls_auto" not in captured

    def test_warns_and_plaintext_when_cert_missing(self, monkeypatch, global_test_env):
        from fastapi import FastAPI
        monkeypatch.setattr(settings, "TELNET_TLS_ENABLED", True)
        monkeypatch.setattr(settings, "SSL_CERTFILE", "/nonexistent/cert.pem")
        captured = {}

        async def _fake(*args, **kwargs):
            captured.update(kwargs)
            return _ServerStub()

        with patch("atheriz.network.telnet.telnetlib3.create_server", side_effect=_fake):
            app = FastAPI()
            lifespan = _mount(app)
            _run_lifespan(lifespan, app)
        assert "ssl" not in captured
        assert "tls_auto" not in captured


class TestTelnetTLSIntegration:
    def _free_port(self):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
        s.close()
        return port

    def test_tls_and_plaintext_coexist_on_same_port(self, monkeypatch, tmp_path, global_test_env):
        _, _, combined = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(combined))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        port = self._free_port()

        async def shell(reader, writer):
            writer.write("hello from secure server\n")
            await asyncio.wait_for(reader.readline(), 10)

        async def run():
            server = await telnetlib3.create_server(
                host="127.0.0.1", port=port, shell=shell,
                ssl=build_telnet_ssl_context(), tls_auto=True,
            )
            try:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                reader, writer = await telnetlib3.open_connection(
                    "127.0.0.1", port, ssl=ctx)
                line = await asyncio.wait_for(reader.readline(), 10)
                assert "hello" in line, f"TLS client failed: {line!r}"
                writer.close()
                reader2, writer2 = await telnetlib3.open_connection("127.0.0.1", port)
                line2 = await asyncio.wait_for(reader2.readline(), 10)
                assert "hello" in line2, f"plain client failed: {line2!r}"
                writer2.close()
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())

    def test_bad_tls_handshake_does_not_kill_server(self, monkeypatch, tmp_path, global_test_env):
        _, _, cert = _make_self_signed(tmp_path)
        monkeypatch.setattr(settings, "SSL_CERTFILE", str(cert))
        monkeypatch.setattr(settings, "SSL_KEYFILE", None)
        port = self._free_port()

        async def shell(reader, writer):
            writer.write("still alive\n")
            await asyncio.sleep(3)

        async def run():
            server = await telnetlib3.create_server(
                host="127.0.0.1", port=port, shell=shell,
                ssl=build_telnet_ssl_context(), tls_auto=True,
            )
            try:
                raw = socket.create_connection(("127.0.0.1", port))
                raw.sendall(b"\x16\x03\x01\x00\x10" + b"\x00" * 16)
                raw.close()
                await asyncio.sleep(0.3)
                reader, writer = await telnetlib3.open_connection("127.0.0.1", port)
                line = await asyncio.wait_for(reader.readline(), 10)
                assert "still alive" in line, line
                writer.close()
            finally:
                server.close()
                await server.wait_closed()

        asyncio.run(run())