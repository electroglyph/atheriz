"""Deterministic deadlock regression tests (replaces the old fixed-10-second
wall-clock stress test, which was timing-based, flaky, and only tested a
liveness symptom rather than the bug).

The deadlock from issue #6 was a lock-order inversion: `Channel.msg` held the
channel lock while delivering to listeners (blocking on a listener's lock),
while `subscribe`/`unsubscribe` held the listener's lock while acquiring the
channel lock.

The fix: `Channel.msg` snapshots the listener list under the channel lock and
broadcasts *outside* the lock. `test_msg_releases_channel_lock_before_delivery`
pins exactly that property deterministically (no timing races — the listener
signals the moment delivery begins). The remaining tests are bounded,
iteration-based smoke checks that must finish within a join timeout.
"""
import random
import threading
import time
from unittest.mock import patch

from atheriz.commands.base_cmdset import CmdSet
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import add_object
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeArea, NodeGrid, NodeLink
from atheriz.utils import Coord


def test_msg_releases_channel_lock_before_delivery(global_test_env):
    """Regression test for the issue #6 lock-order inversion.

    A listener that is still mid-delivery must not hold the channel lock:
    `Channel.msg` is required to snapshot its listeners under the lock and then
    broadcast with the lock released. Under the old implementation the lock was
    held here, so a concurrent `subscribe`/`unsubscribe` (object lock then
    channel lock) could deadlock against the message.
    """
    chan = Channel()
    chan.name = "locktest"
    chan.id = 1000

    delivery_started = threading.Event()
    release_delivery = threading.Event()

    class Listener(Object):
        def msg(self, *args, **kwargs):
            delivery_started.set()
            if not release_delivery.wait(timeout=10):
                raise RuntimeError("test harness timeout")

    listener = Listener()
    listener.id = 1001
    chan.add_listener(listener)

    thread = threading.Thread(target=lambda: chan.msg("hello", listener), daemon=True)
    thread.start()

    assert delivery_started.wait(timeout=10), "message delivery never reached listener"

    acquired = chan.lock.acquire(blocking=False)
    assert acquired, "channel lock still held during listener delivery"
    chan.lock.release()

    release_delivery.set()
    thread.join(timeout=10)
    assert not thread.is_alive(), "delivery thread did not finish"


def test_concurrent_subscribe_unsubscribe_and_msg(global_test_env):
    """Bounded churn across the exact paths from issue #6: subscribe/unsubscribe
    (object lock -> channel lock) racing against message delivery. Each thread
    runs a fixed number of iterations and must finish within the join timeout."""
    chan = Channel()
    chan.name = "churn"
    chan.id = 2000

    objs = []
    for i in range(4):
        o = Object()
        o.id = 3000 + i
        o.name = f"Churner-{i}"
        o.internal_cmdset = CmdSet()
        objs.append(o)
        chan.add_listener(o)

    stop = threading.Event()
    failures = []

    def subscribe_churn():
        for i in range(40):
            if stop.is_set():
                return
            target = objs[i % len(objs)]
            try:
                target.subscribe(chan)
                target.unsubscribe(chan)
            except Exception as exc:  # pragma: no cover - failure path
                failures.append(exc)
                stop.set()

    def messenger():
        for _ in range(40):
            if stop.is_set():
                return
            try:
                chan.msg("tick", objs[0])
            except Exception as exc:  # pragma: no cover - failure path
                failures.append(exc)
                stop.set()

    threads = [threading.Thread(target=subscribe_churn, daemon=True) for _ in range(4)]
    threads.append(threading.Thread(target=messenger, daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)

    assert not any(t.is_alive() for t in threads), "subscribe/msg threads deadlocked"
    assert not failures, failures


def test_move_to_churn_no_deadlock(global_test_env):
    """Bounded real-object churn: movers walking between two rooms (ordered
    location locks + room broadcasts) racing against a looker reading the room.
    Iteration-bounded rather than wall-clock-bounded; a deadlock shows up as a
    thread still alive after the join timeout."""
    room1 = Node(coord=Coord("TestArea", 1, 0, 0), desc="Room 1")
    room1.id = 1
    add_object(room1)
    room2 = Node(coord=Coord("TestArea", 2, 0, 0), desc="Room 2")
    room2.id = 2
    add_object(room2)

    room1.add_link(NodeLink(name="East", coord=room2.coord))
    room2.add_link(NodeLink(name="West", coord=room1.coord))

    nh = get_node_handler()
    nh.add_node(room1)
    nh.add_node(room2)

    movers = []
    for i in range(5):
        npc = Object()
        npc.id = 10 + i
        npc.name = f"Mover-{i}"
        npc.is_npc = True
        npc.internal_cmdset = CmdSet()
        add_object(npc)
        npc.location = room1
        room1.add_object(npc)
        movers.append(npc)

    looker = Object()
    looker.id = 100
    looker.name = "Looker"
    looker.is_npc = True
    looker.internal_cmdset = CmdSet()
    add_object(looker)
    looker.location = room1
    room1.add_object(looker)

    stop = threading.Event()
    failures = []

    def mover_logic(npc):
        for _ in range(15):
            if stop.is_set():
                return
            current_loc = npc.location
            target_link = current_loc.links[0]
            target_node = nh.get_node(target_link.coord)
            try:
                if target_node is not None:
                    npc.move_to(target_node, target_link.name)
            except Exception as exc:  # pragma: no cover - failure path
                failures.append(exc)
                stop.set()
                return
            time.sleep(random.uniform(0.01, 0.03))

    def looker_logic(npc):
        for _ in range(30):
            if stop.is_set():
                return
            try:
                npc.at_look(npc.location)
            except Exception as exc:  # pragma: no cover - failure path
                failures.append(exc)
                stop.set()
                return
            time.sleep(random.uniform(0.005, 0.01))

    threads = [threading.Thread(target=mover_logic, args=(npc,), daemon=True) for npc in movers]
    threads.append(threading.Thread(target=looker_logic, args=(looker,), daemon=True))
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=15)

    assert not any(t.is_alive() for t in threads), "move/look threads deadlocked"
    assert not failures, failures


def test_move_into_deleting_node_not_orphan(global_test_env):
    """Pinned test for moving into a node that is being deleted at the same moment.

    Before the fix, grid removal held Grid.lock while move_to held Node.lock,
    with no shared ordering or deletion flag. A mover could add itself to
    B._contents after B was popped from grid.nodes, ending with location==B
    but B no longer in the world — an orphan. After the fix, move_to holds
    Grid->Node and checks both is_deleted and grid presence, while delete
    marks is_deleted early. One side must win: either the mover gets in before
    the delete and is then relocated with the rest of B's contents, or it
    sees the flag/absence and aborts at the source. It never orphans.
    """
    nh = get_node_handler()
    area = NodeArea("TestDeadlock")
    grid = NodeGrid("TestDeadlock", 0)
    area.add_grid(grid)
    nh.add_area(area)

    coord_a = Coord("TestDeadlock", 0, 0, 0)
    coord_b = Coord("TestDeadlock", 1, 0, 0)
    coord_home = Coord("TestDeadlock", 2, 0, 0)
    node_a = Node(coord=coord_a, desc="A")
    node_b = Node(coord=coord_b, desc="B")
    home = Node(coord=coord_home, desc="home")
    grid.add_node(node_a)
    grid.add_node(node_b)
    grid.add_node(home)

    mover = Object.create(None, "Mover")
    mover.move_to(node_a)
    assert mover.location is node_a

    caller = Object.create(None, "Caller")
    caller.move_to(node_a)
    mover.home = home

    barrier = threading.Barrier(2, timeout=5)
    failures: list[Exception] = []

    def try_move():
        try:
            barrier.wait(timeout=5)
            mover.move_to(node_b)
        except Exception as exc:  # pragma: no cover
            failures.append(exc)

    def try_delete():
        try:
            barrier.wait(timeout=5)
            with patch("atheriz.objects.nodes.get_node_handler", return_value=nh):
                node_b.delete(caller, recursive=False)
        except Exception as exc:  # pragma: no cover
            failures.append(exc)

    t1 = threading.Thread(target=try_move, daemon=True)
    t2 = threading.Thread(target=try_delete, daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=5)
    t2.join(timeout=5)

    assert not t1.is_alive() and not t2.is_alive(), "move/delete threads deadlocked"
    assert not failures, failures

    # Never orphaned in a deleted room.
    b_in_grid = grid.nodes.get((coord_b.x, coord_b.y)) is node_b
    if mover.location is node_b:
        assert b_in_grid, "orphan: mover.location is deleted node B but B not in grid"
        assert not getattr(node_b, "is_deleted", False), "mover in node marked deleted"

    # After delete, moving into the deleted node must fail.
    after = Object.create(None, "After")
    after.move_to(node_a)
    assert after.move_to(node_b) is False
    assert after.location is node_a

    # Cleanup: handler holds references; global_test_env will isolate next test,
    # but explicitly clear our area to avoid leaking into other tests in same process.
    nh.remove_area("TestDeadlock")


def test_add_object_unique_does_not_deadlock_with_contents(global_test_env):
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[2]
    child = r"""
import sys
sys.path.insert(0, {repo!r})
import threading
import time
from pathlib import Path
import tempfile
import os
os.chdir(tempfile.mkdtemp())
Path("settings.py").write_text("")
Path("__init__.py").write_text("")
import atheriz.settings as settings
settings.SAVE_PATH = tempfile.mkdtemp()
from atheriz import database_setup
database_setup._DATABASE = None
database_setup._CLOSED = False
try:
    database_setup.do_setup()
except Exception:
    pass
from atheriz.objects.base_obj import Object
from atheriz.globals.objects import add_object_unique, remove_object, _ALL_OBJECTS
from atheriz.globals.get import get_unique_id
from threading import Barrier

victim = Object.create(None, "Victim")
candidate = Object.create(None, "Candidate")
remove_object(candidate)
assert candidate.id not in _ALL_OBJECTS
barrier = Barrier(2, timeout=5)
deadlock = [False]

def pred(r):
    if r.id == victim.id:
        try:
            barrier.wait(timeout=5)
        except Exception:
            return False
        with r.lock:
            time.sleep(0.05)
            return False
    return False

def adder():
    try:
        add_object_unique(candidate, pred, "dup")
    except Exception:
        pass

def reader():
    try:
        with victim.lock:
            try:
                barrier.wait(timeout=5)
            except Exception:
                return
            _ = victim.contents
    except Exception:
        pass

import threading as th
t1 = th.Thread(target=adder, daemon=True)
t2 = th.Thread(target=reader, daemon=True)
t1.start()
t2.start()
t1.join(timeout=3)
t2.join(timeout=3)
if t1.is_alive() or t2.is_alive():
    print("DEADLOCK=1")
else:
    print("DEADLOCK=0")
"""
    proc = subprocess.run(
        [sys.executable, "-c", child.format(repo=str(repo_root))],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "DEADLOCK=0" in proc.stdout, f"deadlock detected: Global->Object vs Object->Global lock inversion {proc.stdout} {proc.stderr}"
