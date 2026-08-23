#!/usr/bin/env python3
from pathlib import Path

path = Path("extras/gateway/test_gateway.py")
text = path.read_text(encoding="utf-8")
old = '''            def readline(self):
                return self._buf.readline()
'''
new = '''            def readline(self, n=-1):
                return self._buf.readline(n)
'''
count = text.count(old)
if count != 1:
    raise SystemExit(f"SSE fixture: expected exactly one match, got {count}")
path.write_text(text.replace(old, new, 1), encoding="utf-8")
