"""Out-of-band callback collector — "exfil = OOB or it didn't happen".

Ported from elementalsouls/Claude-BugHunter's False-Positive Gate + the
portswigger/embracethered exfil methodology: an injection that tells the model
to fetch a URL is only a confirmed finding when the callback arrives carrying
the canary. Runs a local HTTP sink; each probe gets a unique canary path.
"""
from __future__ import annotations

import json
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class OOBCollector:
    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.requested_port = port
        self.port: int | None = None
        self._hits: list[dict] = []
        self._lock = threading.Lock()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    # ------------------------------------------------------------ lifecycle

    def start(self) -> None:
        collector = self

        class Handler(BaseHTTPRequestHandler):
            def _record(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                entry = {
                    "ts": time.time(),
                    "method": self.command,
                    "path": self.path,
                    "headers": dict(self.headers),
                    "body": body.decode("utf-8", errors="replace"),
                }
                with collector._lock:
                    collector._hits.append(entry)
                self.send_response(200)
                self.send_header("Content-Type", "text/plain")
                self.end_headers()
                self.wfile.write(b"ok")

            def do_GET(self):
                self._record()

            def do_POST(self):
                self._record()

            def log_message(self, *args):
                pass

        self._server = ThreadingHTTPServer((self.host, self.requested_port), Handler)
        self.port = self._server.server_address[1]
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    # ------------------------------------------------------------ canaries

    def canary_url(self, probe_id: str) -> str:
        _token = secrets.token_hex(4)
        return f"http://{self.host}:{self.port}/canary/{probe_id}/{token_hex()}/{token_hex()}"

    def canary_path(self, probe_id: str) -> str:
        return f"/canary/{probe_id}/"

    def wait_for(self, probe_id: str, timeout_s: float = 10.0) -> list[dict]:
        deadline = time.time() + timeout_s
        prefix = self.canary_path(probe_id)
        while time.time() < deadline:
            with self._lock:
                hits = [h for h in self._hits if h["path"].startswith(prefix)]
            if hits:
                return hits
            time.sleep(0.05)
        return []

    def all_hits(self) -> list[dict]:
        with self._lock:
            return list(self._hits)


def token_hex(n: int = 4) -> str:
    return secrets.token_hex(n)


__all__ = ["OOBCollector", "json"]
