"""Issue tests: AsyncThreadPool's task queue is unbounded, allowing the command
queue to grow without limit under load.
"""
from __future__ import annotations

import pytest

from atheriz.globals.asyncthreadpool import AsyncThreadPool


class TestAsyncThreadPool:
    def test_task_queue_is_bounded(self, global_test_env):
        """INTENT: the task queue must have a finite maxsize so a flood of
        commands cannot grow it unboundedly. queue.Queue() with no maxsize is
        unlimited (maxsize == 0)."""
        atp = AsyncThreadPool()
        try:
            assert atp.task_queue.maxsize > 0
        finally:
            atp.stop(True, 10)
