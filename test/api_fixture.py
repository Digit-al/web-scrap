"""Local API test fixture: echo, JSON, XML and error responses.

Run: python test/api_fixture.py   (listens on 127.0.0.1:8098)
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _send(self, status: int, ctype: str, payload: str) -> None:
        data = payload.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _handle(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length).decode("utf-8") if length else ""
        path = self.path.split("?")[0]
        if path == "/api/echo":
            out = {
                "method": self.command,
                "path": self.path,
                "received_headers": {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower()
                    in ("x-test", "content-type", "authorization")
                },
                "body": body,
            }
            self._send(200, "application/json", json.dumps(out))
        elif path == "/api/xml":
            self._send(
                200,
                "application/xml",
                "<root><item>hello</item><item>world</item></root>",
            )
        elif path == "/api/notfound":
            self._send(
                404, "application/json", json.dumps({"error": "not found"})
            )
        else:
            self._send(200, "application/json", json.dumps({"ok": True}))

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _handle

    def log_message(self, *args) -> None:  # silence
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8098), Handler).serve_forever()
