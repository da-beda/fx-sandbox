#!/usr/bin/env python3
from __future__ import annotations

import socket
import threading
import time
import unittest

import stream_cancel


class _Raw:
    def __init__(self, sock: socket.socket) -> None:
        self._sock = sock


class _Fp:
    def __init__(self, sock: socket.socket) -> None:
        self.raw = _Raw(sock)


class _WrappedResponse:
    def __init__(self, sock: socket.socket) -> None:
        self.fp = _Fp(sock)
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class _CloseOnlyResponse:
    def __init__(self) -> None:
        self.close_calls = 0

    def close(self) -> None:
        self.close_calls += 1


class StreamCancellation(unittest.TestCase):
    def test_nested_socket_discovery_reaches_http_wrapper_shape(self):
        left, right = socket.socketpair()
        try:
            response = _WrappedResponse(left)
            found = list(stream_cancel._nested_sockets(response))
            self.assertEqual(found, [left])
        finally:
            left.close()
            right.close()

    def test_abort_upstream_shutdown_unblocks_blocking_read(self):
        upstream_reader, upstream_peer = socket.socketpair()
        response = _WrappedResponse(upstream_reader)
        result: list[bytes | BaseException] = []

        def blocked_read() -> None:
            try:
                result.append(upstream_reader.recv(1))
            except BaseException as exc:  # platform may report EOF or EBADF/reset
                result.append(exc)

        thread = threading.Thread(target=blocked_read)
        thread.start()
        try:
            time.sleep(0.03)
            self.assertTrue(thread.is_alive())
            self.assertTrue(stream_cancel.abort_upstream(response))
            thread.join(timeout=1)
            self.assertFalse(thread.is_alive())
            self.assertTrue(result)
            self.assertEqual(response.close_calls, 0)
        finally:
            upstream_reader.close()
            upstream_peer.close()
            thread.join(timeout=1)

    def test_close_only_response_has_fallback_abort(self):
        response = _CloseOnlyResponse()
        self.assertFalse(stream_cancel.abort_upstream(response))
        self.assertEqual(response.close_calls, 1)

    def test_watcher_aborts_upstream_when_downstream_closes(self):
        downstream_server, downstream_client = socket.socketpair()
        upstream_reader, upstream_peer = socket.socketpair()
        response = _WrappedResponse(upstream_reader)
        try:
            watcher = stream_cancel.DisconnectWatcher(
                downstream_server,
                response,
                poll_interval=0.01,
            ).start()
            downstream_client.close()
            self.assertTrue(watcher.cancelled.wait(1))
            watcher.stop()
            self.assertTrue(upstream_reader.fileno() < 0)
        finally:
            downstream_server.close()
            try:
                downstream_client.close()
            except OSError:
                pass
            upstream_reader.close()
            upstream_peer.close()

    def test_readable_downstream_data_is_not_mistaken_for_disconnect(self):
        downstream_server, downstream_client = socket.socketpair()
        response = _CloseOnlyResponse()
        try:
            watcher = stream_cancel.DisconnectWatcher(
                downstream_server,
                response,
                poll_interval=0.01,
            ).start()
            downstream_client.sendall(b"x")
            time.sleep(0.08)
            self.assertFalse(watcher.cancelled.is_set())
            self.assertEqual(response.close_calls, 0)
            self.assertEqual(downstream_server.recv(1), b"x")
            downstream_client.close()
            self.assertTrue(watcher.cancelled.wait(1))
            watcher.stop()
            self.assertEqual(response.close_calls, 1)
        finally:
            downstream_server.close()
            try:
                downstream_client.close()
            except OSError:
                pass

    def test_watcher_stop_does_not_abort_live_peer(self):
        downstream_server, downstream_client = socket.socketpair()
        response = _CloseOnlyResponse()
        try:
            watcher = stream_cancel.DisconnectWatcher(
                downstream_server,
                response,
                poll_interval=0.01,
            ).start()
            time.sleep(0.05)
            watcher.stop()
            self.assertFalse(watcher.cancelled.is_set())
            self.assertEqual(response.close_calls, 0)
        finally:
            downstream_server.close()
            downstream_client.close()


if __name__ == "__main__":
    unittest.main(verbosity=2)
