"""Small Render bootstrap proxy for Metabase.

Render free instances require a port to open quickly. Metabase can take longer
than that on a 512 MB instance, so this process opens the public port first and
forwards traffic to Metabase once it is ready.
"""

from __future__ import annotations

import http.client
import json
import os
import signal
import socket
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


PUBLIC_PORT = int(os.getenv("PORT", "10000"))
METABASE_HOST = os.getenv("INTERNAL_METABASE_HOST", "127.0.0.1")
METABASE_PORT = int(os.getenv("INTERNAL_METABASE_PORT", "3001"))
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def metabase_is_ready() -> bool:
    try:
        with socket.create_connection((METABASE_HOST, METABASE_PORT), timeout=0.5):
            return True
    except OSError:
        return False


def start_metabase() -> subprocess.Popen[bytes]:
    env = os.environ.copy()
    env["MB_JETTY_HOST"] = METABASE_HOST
    env["MB_JETTY_PORT"] = str(METABASE_PORT)
    command = env.get("METABASE_CMD", "java -jar /app/metabase.jar")
    return subprocess.Popen(command, env=env, shell=True)


class ProxyHandler(BaseHTTPRequestHandler):
    server_version = "uyjoy-metabase-proxy/1.0"

    def do_GET(self) -> None:
        self._handle()

    def do_POST(self) -> None:
        self._handle()

    def do_PUT(self) -> None:
        self._handle()

    def do_PATCH(self) -> None:
        self._handle()

    def do_DELETE(self) -> None:
        self._handle()

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stdout.write("%s - %s\n" % (self.log_date_time_string(), fmt % args))
        sys.stdout.flush()

    def _handle(self) -> None:
        child = getattr(self.server, "metabase_process", None)
        if child is not None and child.poll() is not None:
            self._json(500, {"status": "error", "message": "Metabase exited"})
            return

        if not metabase_is_ready():
            if self.path.startswith("/api/health"):
                self._json(200, {"status": "starting", "metabase": "booting"})
                return
            self.send_response(503)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Retry-After", "10")
            self.end_headers()
            self.wfile.write(
                b"<!doctype html><title>Metabase starting</title>"
                b"<meta http-equiv='refresh' content='10'>"
                b"<body style='font-family:system-ui;padding:32px'>"
                b"<h1>Metabase is starting</h1>"
                b"<p>Please refresh in a few seconds.</p></body>"
            )
            return

        body_length = int(self.headers.get("Content-Length", "0") or "0")
        request_body = self.rfile.read(body_length) if body_length else None
        headers = {
            key: value
            for key, value in self.headers.items()
            if key.lower() not in HOP_BY_HOP_HEADERS and key.lower() != "host"
        }
        headers["Host"] = f"{METABASE_HOST}:{METABASE_PORT}"

        conn = None
        try:
            conn = http.client.HTTPConnection(METABASE_HOST, METABASE_PORT, timeout=120)
            conn.request(self.command, self.path, body=request_body, headers=headers)
            response = conn.getresponse()
            response_body = response.read()
        except Exception as exc:  # pragma: no cover - only used in Render runtime
            self._json(502, {"status": "error", "message": str(exc)})
            return
        finally:
            if conn is not None:
                conn.close()

        self.send_response(response.status, response.reason)
        for key, value in response.getheaders():
            if key.lower() not in HOP_BY_HOP_HEADERS:
                self.send_header(key, value)
        self.end_headers()
        self.wfile.write(response_body)

    def _json(self, status_code: int, payload: dict[str, str]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    child = start_metabase()

    def stop(_signum: int, _frame: object) -> None:
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill()
        raise SystemExit(0)

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    httpd = ThreadingHTTPServer(("0.0.0.0", PUBLIC_PORT), ProxyHandler)
    httpd.metabase_process = child  # type: ignore[attr-defined]
    print(
        f"Proxy listening on :{PUBLIC_PORT}; Metabase booting on "
        f"{METABASE_HOST}:{METABASE_PORT}",
        flush=True,
    )
    httpd.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
