from __future__ import annotations

import secrets
import threading

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


class MapEditResult:
    __slots__ = ("status", "reason", "new_key", "chain")

    def __init__(self, status: str, reason: str = "", new_key: str | None = None, chain: MapEditChain | None = None) -> None:
        self.status = status
        self.reason = reason
        self.new_key = new_key
        self.chain = chain


_chains: dict[str, MapEditChain] = {}
_lock = threading.RLock()


def grant(ip: str, area: str, z: int) -> str:
    """Create a new edit chain and return its initial key."""
    with _lock:
        key = secrets.token_urlsafe(32)
        _chains[key] = MapEditChain(key, ip, area, z)
        return key


def consume(key: str, ip: str, seq: int) -> MapEditResult:
    """Validate one editor message against the key chain.

    Returns PROCESSED with a new key when the message is accepted,
    RETRY with the current key when the message was already accepted
    (ack lost), or REJECT with a reason."""
    with _lock:
        chain = _chains.get(key)
        previous_hit = False
        if chain is None:
            for c in _chains.values():
                if c.previous_key == key:
                    chain = c
                    previous_hit = True
                    break
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
            del _chains[chain.key]
            chain.previous_key = chain.key
            chain.key = new_key
            chain.seq = seq
            _chains[new_key] = chain
            return MapEditResult(PROCESSED, new_key=new_key, chain=chain)
        if seq <= chain.seq:
            return MapEditResult(REJECT, reason="replay")
        return MapEditResult(REJECT, reason="gap")