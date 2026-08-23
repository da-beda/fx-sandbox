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
    "import stream_limits\n",
    "import stream_limits\nimport http_limits\n",
    "HTTP limits import",
)

g = replace_once(
    g,
    '''            try:
                peek = resp.read()
            except Exception:
                peek = b""
''',
    '''            try:
                peek = http_limits.read_limited(
                    resp,
                    http_limits.ERROR_BODY_BYTES,
                    "upstream Responses error body",
                )
            except http_limits.BodyLimitError:
                raise
            except Exception:
                peek = b""
''',
    "Responses fallback error-body limit",
)

g = replace_once(
    g,
    '''        try:
            body = resp.read()
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
''',
    '''        try:
            try:
                body = http_limits.read_limited(
                    resp,
                    http_limits.MODEL_CATALOG_BYTES,
                    "upstream model catalog",
                )
            except http_limits.BodyLimitError as e:
                self._json(502, {"error": str(e)})
                return
            code = getattr(resp, "status", None) or getattr(resp, "code", 200)
''',
    "model catalog body limit",
)

g = replace_once(
    g,
    '''        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b"{}"
''',
    '''        try:
            n = http_limits.parse_content_length(self.headers.get("Content-Length"))
        except http_limits.RequestBodyTooLarge as e:
            self._json(413, {"error": str(e)})
            return
        except http_limits.InvalidContentLength as e:
            self._json(400, {"error": str(e)})
            return
        raw = self.rfile.read(n) if n else b"{}"
''',
    "inbound Gateway body limit",
)

g = replace_once(
    g,
    '''            if code != 200:
                body = resp.read()
                msg = upstream_http_error(code, body)
''',
    '''            if code != 200:
                try:
                    body = http_limits.read_limited(
                        resp,
                        http_limits.ERROR_BODY_BYTES,
                        "upstream error body",
                    )
                    msg = upstream_http_error(code, body)
                except http_limits.BodyLimitError as e:
                    msg = str(e)
''',
    "initial upstream error-body limit",
)

g = replace_once(
    g,
    '''            if not stream:
                body = resp.read()
                if used_responses:
''',
    '''            if not stream:
                try:
                    body = http_limits.read_limited(
                        resp,
                        http_limits.NONSTREAM_COMPLETION_BYTES,
                        "upstream non-stream completion",
                    )
                except http_limits.BodyLimitError as e:
                    self._json(502, {"error": str(e)})
                    return
                if used_responses:
''',
    "non-stream completion limit",
)

g = replace_once(
    g,
    '''                if code != 200:
                    body = resp.read()
                    msg = upstream_http_error(code, body)
                    self._write_events(Stream(allowed).fail(msg))
                    return
''',
    '''                if code != 200:
                    try:
                        body = http_limits.read_limited(
                            resp,
                            http_limits.ERROR_BODY_BYTES,
                            "upstream search-continuation error body",
                        )
                        msg = upstream_http_error(code, body)
                    except http_limits.BodyLimitError as e:
                        msg = str(e)
                    self._write_events(Stream(allowed).fail(msg))
                    return
''',
    "search continuation error-body limit",
)

GATEWAY.write_text(g, encoding="utf-8")
