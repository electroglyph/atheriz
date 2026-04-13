from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

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
        self._render_node()

    def _render_node(self):
        if not self.current_node:
            return
        text, choices_list = self.current_node(self.context)
        self._current_text = text
        self._current_choices = {
            str(choice.key).lower().strip(): choice for choice in choices_list
        }

    def get_display(self) -> str:
        if not self.current_node:
            return ""
        lines = [f"\n{self._current_text}"]
        for choice in self._current_choices.values():
            lines.append(f"  [{choice.key}] {choice.desc}")
        return "\n".join(lines)

    def handle_input(self, user_input: str) -> bool:
        if not self._current_choices:
            self.current_node = None
            return False

        clean_input = str(user_input).lower().strip()
        if clean_input not in self._current_choices:
            return True
        choice = self._current_choices[clean_input]
        if choice.callback:
            choice.callback(self.context)
        if choice.goto:
            self.current_node = choice.goto
            self._render_node()
            return True
        if choice.stay:
            self._render_node()
            return True
        self.current_node = None
        return False

    def close(self):
        self.current_node = None
        self._current_text = ""
        self._current_choices.clear()
        self.context.state.clear()


def run_menu(caller, start_node: MenuNode) -> None:
    from atheriz.globals.get import get_async_threadpool

    engine = MenuEngine(caller, start_node)
    atp = get_async_threadpool()
    try:
        while engine.current_node:
            display = engine.get_display()
            user_input = asyncio.run_coroutine_threadsafe(
                caller.session.prompt(display), atp.loop
            ).result()
            if not engine.handle_input(user_input):
                break
    finally:
        engine.close()
