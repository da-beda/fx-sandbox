#!/usr/bin/env python3
from pathlib import Path

GATEWAY = Path("extras/gateway/gateway.py")


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


g = GATEWAY.read_text(encoding="utf-8")
g = replace_once(
    g,
    "import tool_choice_fidelity\n",
    "import tool_choice_fidelity\nimport stream_cancel\n",
    "stream cancellation import",
)

g = replace_once(
    g,
    '''            try:
                saw_done = False
                for data in read_sse_data(resp):
                    if data.strip() == "[DONE]":
                        saw_done = True
                        break
                    self._write_search_events(conv.consume(data), conv)
                self._write_search_events(conv.close(terminal=saw_done), conv)
            except Exception as e:
                self._write_events(conv.fail(str(e)))
                return
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
''',
    '''            watcher = stream_cancel.DisconnectWatcher(self.connection, resp)
            try:
                with watcher:
                    saw_done = False
                    for data in read_sse_data(resp):
                        if data.strip() == "[DONE]":
                            saw_done = True
                            break
                        self._write_search_events(conv.consume(data), conv)
                    # When fx closes the downstream request, the watcher aborts
                    # the upstream socket to wake a blocking readline(). Do not
                    # try to emit an error/finish onto a connection that is gone.
                    if watcher.cancelled.is_set():
                        return
                    self._write_search_events(conv.close(terminal=saw_done), conv)
            except Exception as e:
                if watcher.cancelled.is_set():
                    return
                self._write_events(conv.fail(str(e)))
                return
            finally:
                try:
                    resp.close()
                except Exception:
                    pass
''',
    "stream cancellation watcher integration",
)

GATEWAY.write_text(g, encoding="utf-8")
