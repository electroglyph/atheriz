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
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK, is_ip_banned
from pathlib import Path
import atheriz.settings as settings


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


def _clamp_naws(rows, cols) -> tuple[int, int]:
    try:
        rows = int(rows)
        cols = int(cols)
    except (TypeError, ValueError):
        return (settings.TELNET_NAWS_MIN_ROWS, settings.TELNET_NAWS_MIN_COLS)
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
    eof = False
    while True:
        chunk = await reader.read(TELNET_INPUT_CHUNK)
        if not chunk:
            eof = True
            break
        buf += chunk
        while True:
            i = _find_eol(buf)
            if i == -1:
                break
            if buf[i] == "\r" and i + 1 >= len(buf) and not eof:
                break
            line = buf[:i]
            rest = buf[i + 1 :]
            if buf[i] == "\r" and rest[:1] in ("\n", "\x00"):
                rest = rest[1:]
            buf = rest
            if dropping or len(line) > max_line:
                yield None
                dropping = False
            else:
                yield line
        effective_len = len(buf)
        if not eof and buf.endswith("\r") and _find_eol(buf) == len(buf) - 1:
            effective_len -= 1
        if effective_len > max_line:
            dropping = True
            buf = ""
    while True:
        i = _find_eol(buf)
        if i == -1:
            break
        line = buf[:i]
        rest = buf[i + 1 :]
        if buf[i] == "\r" and rest[:1] in ("\n", "\x00"):
            rest = rest[1:]
        buf = rest
        if dropping or len(line) > max_line:
            yield None
            dropping = False
        else:
            yield line
    if buf and not dropping:
        if buf == "\r":
            pass
        else:
            if buf.endswith("\r"):
                buf = buf[:-1]
            if buf:
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
        self._pending_bytes = 0
        self._pending_lock = threading.Lock()
        self._closing = False

    def _get_write_buffer_size(self) -> int | None:
        try:
            tr = getattr(self.writer, "transport", None)
            if tr is not None and hasattr(tr, "get_write_buffer_size"):
                buf = tr.get_write_buffer_size()
                if isinstance(buf, int):
                    return buf
            if hasattr(self.writer, "get_write_buffer_size"):
                buf = self.writer.get_write_buffer_size()
                if isinstance(buf, int):
                    return buf
            tr2 = getattr(self.writer, "_transport", None)
            if tr2 is not None and hasattr(tr2, "get_write_buffer_size"):
                buf = tr2.get_write_buffer_size()
                if isinstance(buf, int):
                    return buf
        except Exception:
            return None
        return None

    def _offloop_write(self, text: str, nb: int):
        try:
            buf = self._get_write_buffer_size()
            if buf is not None and buf > settings.TELNET_MAX_PENDING_BYTES:
                logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf} > {settings.TELNET_MAX_PENDING_BYTES}")
                self.close()
                return
            self.writer.write(text)
            buf2 = self._get_write_buffer_size()
            if buf2 is not None and buf2 > settings.TELNET_MAX_PENDING_BYTES:
                logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf2} > {settings.TELNET_MAX_PENDING_BYTES} after write")
                self.close()
        except Exception as e:
            logger.debug(f"[Telnet] write failed for {self.client_host}: {e}")
            self.close()
        finally:
            with self._pending_lock:
                self._pending_bytes = max(0, self._pending_bytes - nb)

    def _offloop_iac(self, telopt_cmd, telopt_opt, nb: int = 0):
        try:
            self.writer.iac(telopt_cmd, telopt_opt)
        except Exception as e:
            logger.debug(f"[Telnet] iac failed for {self.client_host}: {e}")
            self.close()
        finally:
            if nb:
                with self._pending_lock:
                    self._pending_bytes = max(0, self._pending_bytes - nb)

    def send_command(self, cmd: str, *args, **kwargs):
        """
        Telnet clients don't understand JSON arrays like `["prompt", ["text"], {}]`.
        They just read raw text.
        We will translate simple commands and log/ignore unsupported UI functions.
        """
        if self._closing:
            return
        if cmd in ("text", "prompt"):
            text = args[0] if args else ""
            if not text:
                return
            nb = len(text.encode("utf-8"))
            if threading.get_ident() == self.thread_id:
                try:
                    buf = self._get_write_buffer_size()
                    if buf is not None and buf > settings.TELNET_MAX_PENDING_BYTES:
                        logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf} > {settings.TELNET_MAX_PENDING_BYTES}")
                        self.close()
                        return
                    self.writer.write(text)
                    buf2 = self._get_write_buffer_size()
                    if buf2 is not None and buf2 > settings.TELNET_MAX_PENDING_BYTES:
                        logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf2} > {settings.TELNET_MAX_PENDING_BYTES} after write")
                        self.close()
                except Exception as e:
                    logger.debug(f"[Telnet] write failed for {self.client_host}: {e}")
                    self.close()
            else:
                should_close = False
                with self._pending_lock:
                    if self._pending_bytes + nb > settings.TELNET_MAX_PENDING_BYTES:
                        should_close = True
                    else:
                        self._pending_bytes += nb
                if should_close:
                    logger.debug(f"[Telnet] closing {self.client_host}: pending {self._pending_bytes} + {nb} bytes exceeds {settings.TELNET_MAX_PENDING_BYTES}")
                    self.close()
                    return
                try:
                    self._resolve_loop().call_soon_threadsafe(self._offloop_write, text, nb)
                except Exception as e:
                    with self._pending_lock:
                        self._pending_bytes = max(0, self._pending_bytes - nb)
                    logger.debug(f"[Telnet] Error scheduling write for {self.client_host}: {e}")
                    self.close()
        elif cmd == "prompt_masked":
            text = args[0] if args else ""
            nb = len(text.encode("utf-8")) if text else 0
            if threading.get_ident() == self.thread_id:
                try:
                    buf = self._get_write_buffer_size()
                    if buf is not None and buf > settings.TELNET_MAX_PENDING_BYTES:
                        logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf} > {settings.TELNET_MAX_PENDING_BYTES}")
                        self.close()
                        return
                    self.writer.iac(telnetlib3.telopt.WILL, telnetlib3.telopt.ECHO)
                    if text:
                        self.writer.write(text)
                    buf2 = self._get_write_buffer_size()
                    if buf2 is not None and buf2 > settings.TELNET_MAX_PENDING_BYTES:
                        logger.debug(f"[Telnet] closing {self.client_host}: write buffer {buf2} > {settings.TELNET_MAX_PENDING_BYTES} after write")
                        self.close()
                except Exception as e:
                    logger.debug(f"[Telnet] write/iac failed for {self.client_host}: {e}")
                    self.close()
            else:
                if nb:
                    should_close = False
                    with self._pending_lock:
                        if self._pending_bytes + nb > settings.TELNET_MAX_PENDING_BYTES:
                            should_close = True
                        else:
                            self._pending_bytes += nb
                    if should_close:
                        logger.debug(f"[Telnet] closing {self.client_host}: pending {self._pending_bytes} + {nb} bytes exceeds {settings.TELNET_MAX_PENDING_BYTES}")
                        self.close()
                        return
                try:
                    loop = self._resolve_loop()
                    loop.call_soon_threadsafe(self._offloop_iac, telnetlib3.telopt.WILL, telnetlib3.telopt.ECHO)
                    if text:
                        loop.call_soon_threadsafe(self._offloop_write, text, nb)
                    elif nb == 0:
                        pass
                except Exception as e:
                    if nb:
                        with self._pending_lock:
                            self._pending_bytes = max(0, self._pending_bytes - nb)
                    logger.debug(f"[Telnet] Error scheduling prompt_masked for {self.client_host}: {e}")
                    self.close()
        elif cmd == "echo_on":
            try:
                if threading.get_ident() == self.thread_id:
                    self.writer.iac(telnetlib3.telopt.WONT, telnetlib3.telopt.ECHO)
                else:
                    self._resolve_loop().call_soon_threadsafe(self._offloop_iac, telnetlib3.telopt.WONT, telnetlib3.telopt.ECHO)
            except Exception as e:
                logger.debug(f"[Telnet] iac failed for {self.client_host}: {e}")
                self.close()


    def close(self):
        if self._closing:
            return
        self._closing = True
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

            if is_ip_banned(host):
                logger.warning(f"Host {host} in temp ban list has tried to connect.")
                writer.close()
                return

            conn_id = get_connection_manager().generate_connection_id()
            connection = TelnetConnection(reader, writer, session_id=conn_id)
            if not get_connection_manager().register_connection(conn_id, connection):
                return

            # Initialize terminal size if possible
            writer.write("\r\n\x1b[1;1H\x1b[2J")  # Clear screen

            def on_naws(rows, cols):
                if type(rows) is not int or type(cols) is not int:
                    return
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
