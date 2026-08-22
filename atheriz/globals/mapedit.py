from __future__ import annotations

import secrets
import threading
import time

import atheriz.settings as settings

PROCESSED = "processed"
RETRY = "retry"
REJECT = "reject"


class MapEditChain:
    def __init__(self, key: str, ip: str, area: str, z: int) -> None:
        self.key = key
        self.previous_key = ""
        self.seq = -1
        self.ip = ip
        self.area = area
        self.z = z
        self.validation: list[int] | None = None
        self.created = time.monotonic()


class MapEditResult:
    __slots__ = ("status", "reason", "new_key", "chain")

    def __init__(self, status: str, reason: str = "", new_key: str | None = None, chain: MapEditChain | None = None) -> None:
        self.status = status
        self.reason = reason
        self.new_key = new_key
        self.chain = chain


_chains: dict[str, MapEditChain] = {}
_previous: dict[str, str] = {}
_lock = threading.RLock()


def _evict(now: float) -> None:
    ttl = getattr(settings, "MAPEDIT_CHAIN_TTL", 60.0) * 60.0
    cap = getattr(settings, "MAPEDIT_MAX_CHAINS", 256)
    if ttl > 0:
        expired = [k for k, c in list(_chains.items()) if now - getattr(c, "created", now) > ttl]
        for k in expired:
            c = _chains.pop(k, None)
            if c is not None:
                _previous.pop(c.previous_key, None)
    stale = [p for p, cur in list(_previous.items()) if cur not in _chains]
    for p in stale:
        _previous.pop(p, None)
    while len(_chains) > cap:
        oldest = min(_chains, key=lambda k: getattr(_chains[k], "created", 0))
        c = _chains.pop(oldest, None)
        if c is not None:
            _previous.pop(c.previous_key, None)
        stale = [p for p, cur in list(_previous.items()) if cur not in _chains]
        for p in stale:
            _previous.pop(p, None)


def grant(ip: str, area: str, z: int) -> str:
    with _lock:
        _evict(time.monotonic())
        key = secrets.token_urlsafe(32)
        _chains[key] = MapEditChain(key, ip, area, z)
        if len(_chains) > getattr(settings, "MAPEDIT_MAX_CHAINS", 256):
            _evict(time.monotonic())
        return key


def consume(key: str, ip: str, seq: int) -> MapEditResult:
    with _lock:
        _evict(time.monotonic())
        chain = _chains.get(key)
        previous_hit = False
        if chain is None:
            cur = _previous.get(key)
            if cur is not None:
                c = _chains.get(cur)
                if c is not None:
                    chain = c
                    previous_hit = True
                else:
                    _previous.pop(key, None)
        if chain is None:
            return MapEditResult(REJECT, reason="unknown_key")
        if chain.ip != ip:
            return MapEditResult(REJECT, reason="ip")
        if previous_hit:
            if seq == chain.seq:
                return MapEditResult(RETRY, new_key=chain.key, chain=chain)
            return MapEditResult(REJECT, reason="replay")
        if seq == chain.seq + 1:
            new_key = secrets.token_urlsafe(32)
            old_key = chain.key
            del _chains[old_key]
            _previous.pop(old_key, None)
            chain.previous_key = old_key
            chain.key = new_key
            chain.seq = seq
            _chains[new_key] = chain
            _previous[old_key] = new_key
            return MapEditResult(PROCESSED, new_key=new_key, chain=chain)
        if seq <= chain.seq:
            return MapEditResult(REJECT, reason="replay")
        return MapEditResult(REJECT, reason="gap")