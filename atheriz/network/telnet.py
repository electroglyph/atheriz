from __future__ import annotations
import asyncio
import ssl
import threading
from contextlib import asynccontextmanager
from fastapi import FastAPI
import telnetlib3
from .protocol import BaseProtocol
from .connection import BaseConnection
from atheriz.globals.get import get_connection_manager
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK
from pathlib import Path
import atheriz.settings as settings
import time


def build_telnet_ssl_context() -> ssl.SSLContext | None:
    certfile = getattr(settings, "SSL_CERTFILE", None)
    if not certfile:
        return None
    if not Path(certfile).is_file():
        logger.warning(f"WARNING: SSL cert file not found: {certfile}")
        return None
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    keyfile = getattr(settings, "SSL_KEYFILE", None)
    try:
        context.load_cert_chain(certfile, keyfile=keyfile)
    except (ssl.SSLError, OSError) as e:
        logger.warning(f"WARNING: Could not load telnet TLS cert: {e}")
        return None
    return context


def _clamp_naws(rows: int, cols: int) -> tuple[int, int]:
    """Clamp terminal dimensions to reasonable bounds."""
    return (
        max(settings.TELNET_NAWS_MIN_ROWS, min(rows, settings.TELNET_NAWS_MAX_ROWS)),
        max(settings.TELNET_NAWS_MIN_COLS, min(cols, settings.TELNET_NAWS_MAX_COLS)),
    )

TELNET_INPUT_CHUNK = 4096


def _find_eol(buf: str) -> int:
    idx = buf.find("\r")
    nl = buf.find("\n")
    if idx == -1:
        return nl
    if nl == -1:
        return idx
    return min(idx, nl)


async def read_capped_lines(reader, max_line: int):
    """Yield complete telnet input lines from `reader` (CR, LF, CR LF, and
    CR NUL terminators, matching telnetlib3's readline semantics, terminators
    stripped). A line whose pending content exceeds `max_line` is discarded:
    `None` is yielded at its terminator and memory stays bounded."""
    buf = ""
    dropping = False
    while True:
        chunk = await reader.read(TELNET_INPUT_CHUNK)
        if not chunk:
            break
        buf += chunk
        while True:
            i = _find_eol(buf)
            if i == -1:
                break
            line = buf[:i]
            rest = buf[i + 1 :]
            if buf[i] == "\r" and (rest.startswith("\n") or rest.startswith("\x00")):
                rest = rest[1:]
            buf = rest
            if dropping or len(line) > max_line:
                yield None
                dropping = False
            else:
                yield line
        if len(buf) > max_line:
            dropping = True
            buf = ""
    if buf and not dropping:
        yield buf

class TelnetConnection(BaseConnection):
    """
    Telnet-specific implementation of the BaseConnection.
    """
    def __init__(self, reader, writer, session_id: str | None = None):
        super().__init__(session_id)
        self.reader = reader
        self.writer = writer
        self.client_host = "?"
        try:
            self.client_host = writer.get_extra_info("peername")[0]
        except Exception:
            pass

    def send_command(self, cmd: str, *args, **kwargs):
        """
        Telnet clients don't understand JSON arrays like `["prompt", ["text"], {}]`.
        They just read raw text.
        We will translate simple commands and log/ignore unsupported UI functions.
        """
        if cmd in ("text", "prompt"):
            text = args[0] if args else ""
            try:
                if threading.get_ident() == self.thread_id:
                    self.writer.write(text)
                else:
                    self._resolve_loop().call_soon_threadsafe(self.writer.write, text)
            except Exception:
                pass


    def close(self):
        try:
            if threading.get_ident() == self.thread_id:
                self.writer.close()
            else:
                self._resolve_loop().call_soon_threadsafe(self.writer.close)
        except Exception as e:
            logger.debug(f"[Telnet] Error closing connection: {e}")


class TelnetProtocol(BaseProtocol):
    """
    Sets up telnetlib3 server via a FastAPI lifespan/startup event task.
    """
    @classmethod
    def setup(cls, app: FastAPI):
        if not getattr(settings, "TELNET_ENABLED", False):
            return

        previous_lifespan = app.router.lifespan_context
        server_task = None

        async def shell(reader, writer):
            host = "?"
            try:
                host = writer.get_extra_info("peername")[0]
            except Exception:
                pass

            with TEMP_BANNED_LOCK:
                if host in TEMP_BANNED_IPS:
                    if time.time() < TEMP_BANNED_IPS[host]:
                        logger.warning(f"Host {host} in temp ban list has tried to connect.")
                        writer.close()
                        return
                    else:
                        del TEMP_BANNED_IPS[host]

                conn_id = get_connection_manager().generate_connection_id()
                connection = TelnetConnection(reader, writer, session_id=conn_id)
                if not get_connection_manager().register_connection(conn_id, connection):
                    return

            # Initialize terminal size if possible
            writer.write("\r\n\x1b[1;1H\x1b[2J")  # Clear screen

            def on_naws(rows, cols):
                if connection.session:
                    rows, cols = _clamp_naws(rows, cols)
                    connection.session.term_width = cols
                    connection.session.term_height = rows

            # ask the client to report window size
            writer.set_ext_callback(telnetlib3.telopt.NAWS, on_naws)
            writer.iac(telnetlib3.telopt.DO, telnetlib3.telopt.NAWS)

            # mock a client_ready command since webclient normally sends it
            get_connection_manager().dispatch(connection, "client_ready", [], {})
            try:
                max_line = getattr(settings, "TELNET_MAX_LINE", 65536)
                async for line in read_capped_lines(reader, max_line):
                    if line is None:
                        logger.warning(f"[Telnet] dropped overlong input line from {conn_id}")
                        continue
                    get_connection_manager().dispatch(connection, "text", [line.strip()], {})
            except asyncio.CancelledError:
                pass
            except Exception as e:
                logger.error(f"[Telnet] Error in shell for {conn_id}: {e}")
            finally:
                get_connection_manager().disconnect(connection)

        @asynccontextmanager
        async def run_telnet_server():
            nonlocal server_task
            port = getattr(settings, "TELNET_PORT", 4000)
            interface = getattr(settings, "TELNET_INTERFACE", "0.0.0.0")

            kwargs = {
                "port": port,
                "host": interface,
                "shell": shell,
                "timeout": getattr(settings, "TELNET_CONNECTION_TIMEOUT", 300),
            }
            tls_context = None
            if getattr(settings, "TELNET_TLS_ENABLED", False):
                tls_context = build_telnet_ssl_context()
                if tls_context is not None:
                    kwargs["ssl"] = tls_context
                    kwargs["tls_auto"] = True
                    logger.info(
                        f"SSL is enabled for telnet (cert: {settings.SSL_CERTFILE}) with "
                        "auto-detection for plaintext clients"
                    )
                else:
                    logger.warning("TELNET_TLS_ENABLED is on but no usable cert — running plaintext")

            logger.info(f"Starting Telnet Protocol on {interface}:{port}")
            server_task = await telnetlib3.create_server(**kwargs)
            try:
                yield
            finally:
                if server_task:
                    server_task.close()
                    await server_task.wait_closed()
                    logger.info("Telnet Protocol server stopped.")

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            if previous_lifespan is not None:
                async with previous_lifespan(app):
                    async with run_telnet_server():
                        yield
            else:
                async with run_telnet_server():
                    yield

        app.router.lifespan_context = lifespan
