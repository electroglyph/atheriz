import asyncio
import threading
from fastapi import FastAPI
import telnetlib3
from .protocol import BaseProtocol
from .connection import BaseConnection
from . import connection_manager
from atheriz.logger import logger
from atheriz.globals.objects import TEMP_BANNED_IPS, TEMP_BANNED_LOCK
import atheriz.settings as settings
import time

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
                    self.loop.call_soon_threadsafe(self.writer.write, text)
            except Exception:
                pass


    def close(self):
        try:
            if threading.get_ident() == self.thread_id:
                self.writer.close()
            else:
                self.loop.call_soon_threadsafe(self.writer.close)
        except Exception as e:
            logger.debug(f"[Telnet] Error closing connection: {e}")


class TelnetProtocol(BaseProtocol):
    """
    Sets up telnetlib3 server via a FastAPI lifespan/startup event task.
    """
    _server_task = None
    
    @classmethod
    def setup(cls, app: FastAPI):
        if not getattr(settings, "TELNET_ENABLED", False):
            return

        @app.on_event("startup")
        async def startup_event():
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

                conn_id = connection_manager.generate_connection_id()
                connection = TelnetConnection(reader, writer, session_id=conn_id)
                connection_manager.register_connection(conn_id, connection)

                # Initialize terminal size if possible
                writer.write("\r\n\x1b[1;1H\x1b[2J")  # Clear screen clear connection initial artifacts
                
                def on_naws(rows, cols):
                    if connection.session:
                        connection.session.term_width = cols
                        connection.session.term_height = rows
                        # try:
                        #     connection.send_command("text", f"[DEBUG] Terminal size updated: {cols}x{rows}\r\n")
                        # except Exception:
                        #     pass
                
                # Ask the client to report window size
                writer.set_ext_callback(telnetlib3.telopt.NAWS, on_naws)
                writer.iac(telnetlib3.telopt.DO, telnetlib3.telopt.NAWS)

                # We mock a client_ready command since webclient normally sends it
                connection_manager.dispatch(connection, "client_ready", [], {})

                try:
                    while True:
                        inp = await reader.readline()
                        if not inp:
                            break
                        connection_manager.dispatch(connection, "text", [inp.strip()], {})
                except asyncio.CancelledError:
                    pass
                except Exception as e:
                    logger.error(f"[Telnet] Error in shell for {conn_id}: {e}")
                finally:
                    connection_manager.disconnect(connection)

            port = getattr(settings, "TELNET_PORT", 4000)
            interface = getattr(settings, "TELNET_INTERFACE", "0.0.0.0")

            logger.info(f"Starting Telnet Protocol on {interface}:{port}")
            cls._server_task = await telnetlib3.create_server(
                port=port, 
                host=interface, 
                shell=shell,
                timeout=0
            )
            
        @app.on_event("shutdown")
        async def shutdown_event():
            if cls._server_task:
                cls._server_task.close()
                await cls._server_task.wait_closed()
                logger.info("Telnet Protocol server stopped.")
