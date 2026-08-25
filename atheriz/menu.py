from __future__ import annotations

import asyncio
import concurrent.futures
import inspect
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

from atheriz import settings
from atheriz.logger import logger

MenuNode = Callable[["MenuContext"], tuple[str, list["Choice"]]]


@dataclass
class MenuContext:
    caller: Any
    state: dict = field(default_factory=dict)


@dataclass
class Choice:
    key: str
    desc: str
    goto: Optional[MenuNode] = None
    callback: Optional[Callable[["MenuContext"], Any]] = None
    stay: bool = False


class MenuEngine:
    def __init__(self, caller, start_node: MenuNode):
        self.context = MenuContext(caller=caller)
        self.current_node: Optional[MenuNode] = start_node
        self._current_text: str = ""
        self._current_choices: dict[str, Choice] = {}
        if start_node is not None and not inspect.iscoroutinefunction(start_node):
            self._render_node()

    def _render_node(self):
        if not self.current_node:
            return
        if inspect.iscoroutinefunction(self.current_node):
            raise RuntimeError("async menu node requires async render")
        text, choices_list = self.current_node(self.context)
        self._current_text = text
        self._current_choices = {}
        for choice in choices_list:
            key = str(choice.key).lower().strip()
            if key in self._current_choices:
                raise ValueError(f"duplicate menu key: {choice.key!r}")
            self._current_choices[key] = choice

    async def _render_node_async(self):
        if not self.current_node:
            return
        if inspect.iscoroutinefunction(self.current_node):
            text, choices_list = await self.current_node(self.context)
        else:
            text, choices_list = self.current_node(self.context)
        self._current_text = text
        self._current_choices = {}
        for choice in choices_list:
            key = str(choice.key).lower().strip()
            if key in self._current_choices:
                raise ValueError(f"duplicate menu key: {choice.key!r}")
            self._current_choices[key] = choice

    def get_display(self) -> str:
        if not self.current_node:
            return ""
        lines = [f"\n{self._current_text}"]
        for choice in self._current_choices.values():
            lines.append(f"  [{choice.key}] {choice.desc}")
        return "\r\n".join(lines)

    def handle_input(self, user_input: str) -> bool:
        if not self._current_choices:
            self.current_node = None
            return False

        clean_input = str(user_input).lower().strip()
        if clean_input not in self._current_choices:
            return True
        choice = self._current_choices[clean_input]
        if choice.callback:
            try:
                if inspect.iscoroutinefunction(choice.callback):
                    raise RuntimeError("async callback requires async handle_input")
                choice.callback(self.context)
            except Exception:
                logger.error("menu callback failed", exc_info=True)
        if choice.goto:
            self.current_node = choice.goto
            self._render_node()
            return True
        if choice.stay:
            self._render_node()
            return True
        self.current_node = None
        return False

    async def handle_input_async(self, user_input: str) -> bool:
        if not self._current_choices:
            self.current_node = None
            return False
        clean_input = str(user_input).lower().strip()
        if clean_input not in self._current_choices:
            return True
        choice = self._current_choices[clean_input]
        if choice.callback:
            try:
                if inspect.iscoroutinefunction(choice.callback):
                    await choice.callback(self.context)
                else:
                    choice.callback(self.context)
            except Exception:
                logger.error("menu callback failed", exc_info=True)
        if choice.goto:
            self.current_node = choice.goto
            await self._render_node_async()
            return True
        if choice.stay:
            await self._render_node_async()
            return True
        self.current_node = None
        return False

    def close(self):
        self.current_node = None
        self._current_text = ""
        self._current_choices.clear()
        self.context.state.clear()


def run_menu(caller, start_node: MenuNode) -> concurrent.futures.Future:
    from atheriz.globals.get import get_async_threadpool

    atp = get_async_threadpool()

    async def _runner():
        engine = MenuEngine(caller, start_node)
        if engine.current_node is not None and engine._current_text == "" and not engine._current_choices:
            try:
                await engine._render_node_async()
            except Exception:
                logger.error("menu initial render failed", exc_info=True)
                engine.close()
                return
        try:
            while engine.current_node:
                display = engine.get_display()
                try:
                    user_input = await asyncio.wait_for(
                        caller.session.prompt(display), timeout=settings.MENU_PROMPT_TIMEOUT
                    )
                except (asyncio.TimeoutError, asyncio.CancelledError, concurrent.futures.CancelledError):
                    break
                try:
                    keep_going = await engine.handle_input_async(user_input)
                except Exception:
                    logger.error("menu handle_input failed", exc_info=True)
                    break
                if not keep_going:
                    break
        finally:
            engine.close()

    coro = _runner()
    try:
        future = asyncio.run_coroutine_threadsafe(coro, atp.loop)
    except Exception:
        try:
            coro.close()
        except Exception:
            pass
        logger.error("run_menu schedule failed", exc_info=True)
        dummy: concurrent.futures.Future = concurrent.futures.Future()
        dummy.set_result(None)
        return dummy

    def _log_error(fut: concurrent.futures.Future):
        try:
            exc = fut.exception()
        except Exception:
            return
        if exc is not None:
            logger.error(f"menu runner failed: {exc}", exc_info=True)

    future.add_done_callback(_log_error)
    return future
