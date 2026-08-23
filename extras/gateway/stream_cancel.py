#!/usr/bin/env python3
"""Abort a blocking upstream model stream when the downstream fx client leaves.

The optional Gateway adapter is a proxy: fx owns the downstream loopback HTTP
connection while urllib/http.client owns an independent upstream provider
connection. A cancellation in fx closes the downstream request, but a blocking
upstream ``readline()`` otherwise has no reason to wake until its long socket
timeout expires.

This module watches only for downstream EOF. It never consumes downstream bytes.
When EOF is observed it shuts down the socket nested inside the urllib response,
which interrupts a blocking upstream read without imposing a short first-token or
idle timeout on slow local models.
"""
from __future__ import annotations

import select
import socket
import threading
from typing import Any, Iterable

_SOCKET_ATTRS = ("fp", "raw", "_sock", "sock", "socket")


def _nested_sockets(root: Any, max_depth: int = 5) -> Iterable[socket.socket]:
    """Yield sockets reachable through the bounded urllib/http.client wrapper chain."""
    stack: list[tuple[Any, int]] = [(root, 0)]
    seen: set[int] = set()
    yielded: set[int] = set()
    while stack:
        obj, depth = stack.pop()
        if obj is None:
            continue
        oid = id(obj)
        if oid in seen:
            continue
        seen.add(oid)
        if isinstance(obj, socket.socket):
            if oid not in yielded:
                yielded.add(oid)
                yield obj
            continue
        if depth >= max_depth:
            continue
        for name in _SOCKET_ATTRS:
            try:
                child = getattr(obj, name)
            except Exception:
                continue
            if child is not None:
                stack.append((child, depth + 1))


def abort_upstream(response: Any) -> bool:
    """Best-effort socket abort for a urllib response; return whether a socket was found."""
    found = False
    for sock in _nested_sockets(response):
        found = True
        try:
            sock.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            sock.close()
        except OSError:
            pass
    if not found:
        # A test double or unusual response wrapper may expose only close().
        # Avoid calling response.close() when a real socket was found because
        # file-object close can contend with a blocking read in another thread.
        try:
            response.close()
        except Exception:
            pass
    return found


def peer_disconnected(sock: socket.socket) -> bool:
    """Return True only for EOF/error; readable application bytes are left untouched."""
    try:
        readable, _, _ = select.select([sock], [], [], 0)
    except (OSError, ValueError):
        return True
    if not readable:
        return False
    try:
        data = sock.recv(1, socket.MSG_PEEK)
    except (BlockingIOError, InterruptedError):
        return False
    except OSError:
        return True
    return data == b""


class DisconnectWatcher:
    """Watch a downstream socket and abort one upstream response on disconnect."""

    def __init__(
        self,
        downstream: socket.socket,
        upstream_response: Any,
        *,
        poll_interval: float = 0.05,
    ) -> None:
        self.downstream = downstream
        self.upstream_response = upstream_response
        self.poll_interval = max(0.01, float(poll_interval))
        self.cancelled = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> "DisconnectWatcher":
        if self._thread is not None:
            return self
        self._thread = threading.Thread(
            target=self._run,
            name="fxs-upstream-cancel-watch",
            daemon=True,
        )
        self._thread.start()
        return self

    def stop(self) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=max(0.25, self.poll_interval * 4))

    def __enter__(self) -> "DisconnectWatcher":
        return self.start()

    def __exit__(self, *_exc: Any) -> None:
        self.stop()

    def _run(self) -> None:
        while not self._stop.wait(self.poll_interval):
            if not peer_disconnected(self.downstream):
                continue
            self.cancelled.set()
            abort_upstream(self.upstream_response)
            return
