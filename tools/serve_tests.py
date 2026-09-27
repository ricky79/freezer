"""Serve il repository su http://127.0.0.1:8766 per i test JS nel browser."""

import functools
import http.server
import mimetypes
from pathlib import Path

# Su Windows il registro può associare .js a text/plain e i moduli ES non partirebbero.
mimetypes.add_type("text/javascript", ".js")

ROOT = Path(__file__).resolve().parent.parent

if __name__ == "__main__":
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(ROOT))
    print("Test JS: http://127.0.0.1:8766/tests/js/test.html")
    http.server.ThreadingHTTPServer(("127.0.0.1", 8766), handler).serve_forever()
