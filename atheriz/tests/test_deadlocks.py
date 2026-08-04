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

from atheriz.commands.base_cmdset import CmdSet
from atheriz.globals.get import get_node_handler
from atheriz.globals.objects import add_object
from atheriz.objects.base_channel import Channel
from atheriz.objects.base_obj import Object
from atheriz.objects.nodes import Node, NodeLink
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
