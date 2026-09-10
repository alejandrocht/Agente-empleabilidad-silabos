"""Bounded, process-local conversational memory for successful CIAR turns."""

from __future__ import annotations

import asyncio
import hashlib
import heapq
import hmac
import secrets
import threading
import time
from collections import OrderedDict, deque
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TypeGuard
from weakref import WeakKeyDictionary

from agente.utils.validacion import MAX_PREGUNTA_CHARS

DEFAULT_TTL_SECONDS = 30 * 60
DEFAULT_MAX_TURNS = 4
DEFAULT_MAX_SCOPES = 256
DEFAULT_MAX_ENTRIES = 512
_PROCESS_MEMORY_SECRET = secrets.token_bytes(32)


class _TrustedMemoryScope(str):
    """Capability minted in-process; JSON clients can only provide plain strings."""


@dataclass(frozen=True)
class ConversationTurn:
    original_question: str
    created_at: float


@dataclass
class _ScopeGate:
    lock: asyncio.Lock
    users: int = 0


class ConversationMemory:
    """Keep minimal successful turns with global age and capacity bounds."""

    def __init__(
        self,
        *,
        ttl_seconds: float = DEFAULT_TTL_SECONDS,
        max_turns: int = DEFAULT_MAX_TURNS,
        max_scopes: int = DEFAULT_MAX_SCOPES,
        max_entries: int = DEFAULT_MAX_ENTRIES,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if ttl_seconds <= 0:
            raise ValueError("ttl_seconds must be positive")
        if max_turns <= 0:
            raise ValueError("max_turns must be positive")
        if max_scopes <= 0:
            raise ValueError("max_scopes must be positive")
        if max_entries <= 0:
            raise ValueError("max_entries must be positive")
        self._ttl_seconds = ttl_seconds
        self._max_turns = max_turns
        self._max_scopes = max_scopes
        self._max_entries = max_entries
        self._clock = clock
        self._turns: OrderedDict[str, deque[ConversationTurn]] = OrderedDict()
        self._entry_count = 0
        self._expirations: list[tuple[float, str]] = []
        self._scope_gates: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, _ScopeGate]] = (
            WeakKeyDictionary()
        )
        self._lock = threading.RLock()

    def _drop_scope(self, scope: str) -> None:
        turns = self._turns.pop(scope, None)
        if turns is not None:
            self._entry_count -= len(turns)

    def _prune_scope(self, scope: str, now: float) -> None:
        turns = self._turns.get(scope)
        if turns is None:
            return
        cutoff = now - self._ttl_seconds
        while turns and turns[0].created_at <= cutoff:
            turns.popleft()
            self._entry_count -= 1
        if not turns:
            self._turns.pop(scope, None)

    def _rebuild_expirations(self) -> None:
        self._expirations = [
            (turns[0].created_at + self._ttl_seconds, scope)
            for scope, turns in self._turns.items()
            if turns
        ]
        heapq.heapify(self._expirations)

    def _schedule_expiration(self, scope: str) -> None:
        turns = self._turns.get(scope)
        if not turns:
            return
        heapq.heappush(
            self._expirations,
            (turns[0].created_at + self._ttl_seconds, scope),
        )
        if len(self._expirations) > max(16, len(self._turns) * 2):
            self._rebuild_expirations()

    def _sweep_expired(self, now: float) -> None:
        while self._expirations and self._expirations[0][0] <= now:
            expires_at, scope = heapq.heappop(self._expirations)
            turns = self._turns.get(scope)
            if not turns:
                continue
            current_expiry = turns[0].created_at + self._ttl_seconds
            if current_expiry != expires_at:
                continue
            self._prune_scope(scope, now)
            self._schedule_expiration(scope)

    def _enforce_capacity(self) -> None:
        scopes_with_new_head: set[str] = set()
        while len(self._turns) > self._max_scopes:
            scope = next(iter(self._turns))
            self._drop_scope(scope)
        while self._entry_count > self._max_entries and self._turns:
            scope = next(iter(self._turns))
            turns = self._turns[scope]
            turns.popleft()
            self._entry_count -= 1
            if not turns:
                self._turns.pop(scope, None)
                scopes_with_new_head.discard(scope)
            else:
                scopes_with_new_head.add(scope)
        for scope in scopes_with_new_head:
            self._schedule_expiration(scope)
        if len(self._expirations) > max(16, len(self._turns) * 2):
            self._rebuild_expirations()

    def remember(
        self,
        scope: str,
        original_question: str,
    ) -> None:
        """Store the original question with bounded age and capacity limits."""
        if not scope or not original_question:
            return
        now = self._clock()
        with self._lock:
            self._sweep_expired(now)
            turns = self._turns.get(scope)
            turn = ConversationTurn(
                original_question=original_question[:MAX_PREGUNTA_CHARS],
                created_at=now,
            )
            if turns is None:
                turns = deque()
                self._turns[scope] = turns
            else:
                self._turns.move_to_end(scope)
            turns.append(turn)
            self._entry_count += 1
            while len(turns) > self._max_turns:
                turns.popleft()
                self._entry_count -= 1
            self._schedule_expiration(scope)
            self._enforce_capacity()

    def history(self, scope: str) -> tuple[ConversationTurn, ...]:
        if not scope:
            return ()
        now = self._clock()
        with self._lock:
            self._sweep_expired(now)
            turns = self._turns.get(scope)
            if turns is None:
                return ()
            self._turns.move_to_end(scope)
            return tuple(turns)

    def stats(self) -> dict[str, int]:
        """Return bounded aggregate counts without exposing scope identifiers."""
        now = self._clock()
        with self._lock:
            self._sweep_expired(now)
            return {"scopes": len(self._turns), "entries": self._entry_count}

    @asynccontextmanager
    async def serialized_scope(self, scope: str) -> AsyncIterator[None]:
        """Serialize the read-context/write-turn cycle for one trusted scope."""
        if not is_trusted_memory_scope(scope):
            yield
            return
        loop = asyncio.get_running_loop()
        with self._lock:
            gates = self._scope_gates.setdefault(loop, {})
            gate = gates.get(scope)
            if gate is None:
                gate = _ScopeGate(asyncio.Lock())
                gates[scope] = gate
            gate.users += 1
        try:
            async with gate.lock:
                yield
        finally:
            with self._lock:
                gate.users -= 1
                if gate.users == 0:
                    gates.pop(scope, None)
                if not gates:
                    self._scope_gates.pop(loop, None)

    def clear(self) -> None:
        with self._lock:
            self._turns.clear()
            self._expirations.clear()
            self._entry_count = 0


def derive_memory_scope(
    secret: str | bytes,
    user_identity: str,
    conversation_id: str,
) -> str:
    """Derive an opaque in-process capability without retaining raw identity."""
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    payload = f"{user_identity}\x00{conversation_id}".encode()
    digest = hmac.new(key, payload, hashlib.sha256).hexdigest()
    return _TrustedMemoryScope(digest)


def is_trusted_memory_scope(value: object) -> TypeGuard[_TrustedMemoryScope]:
    return isinstance(value, _TrustedMemoryScope)


def server_memory_scope(user_identity: str, conversation_id: str) -> str:
    return derive_memory_scope(_PROCESS_MEMORY_SECRET, user_identity, conversation_id)

DEFAULT_CONVERSATION_MEMORY = ConversationMemory()
