from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, HTTPServer

from .fix_mapper import apply_argus_payload


class Handler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        fix_key = apply_argus_payload(payload)
        body = json.dumps({"ok": bool(fix_key), "fix_key": fix_key}).encode("utf-8")
        self.send_response(200 if fix_key else 202)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    server = HTTPServer(("127.0.0.1", 8787), Handler)
    print("Listening for Argus fix webhooks on http://127.0.0.1:8787")
    server.serve_forever()


if __name__ == "__main__":
    main()

