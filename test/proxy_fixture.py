"""Minimal HTTP forward-proxy test fixture (port 8097).

Instead of forwarding, it records that the traffic was routed through
the proxy (absolute-form request line + marker payload).

Run: python test/proxy_fixture.py
"""
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class Handler(BaseHTTPRequestHandler):
    def _proxy_answer(self) -> None:
        payload = json.dumps(
            {
                "via_proxy": True,
                "requested": self.path,  # absolute URL in proxy mode
                "method": self.command,
            }
        )
        data = payload.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _proxy_answer

    def log_message(self, *args) -> None:  # silence
        pass


if __name__ == "__main__":
    ThreadingHTTPServer(("127.0.0.1", 8097), Handler).serve_forever()
