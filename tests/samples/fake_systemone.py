"""A deterministic, stdlib-only stand-in for the System One ``noul`` endpoint.

Used by tests/samples/run.sh so the sample pipes run without an API key or
network. Each POST to /v1/systemone is appended to --log as one JSON line and
answered with a score picked by --rules: the first rules key found in the
question selects a list of regex patterns, tried in order against the
JSON-encoded state; the first match gives the noul, otherwise 0.05.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import signal
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

PATH = "/v1/systemone"
DEFAULT_NOUL = 0.05


def score(rules: dict[str, list[dict[str, Any]]], instructions: str, state: Any) -> float:
    text = json.dumps(state, sort_keys=True, ensure_ascii=False)
    for key, patterns in rules.items():
        if key in instructions:
            for rule in patterns:
                if re.search(rule["pattern"], text, re.IGNORECASE):
                    return float(rule["noul"])
            return DEFAULT_NOUL
    return DEFAULT_NOUL


class Handler(BaseHTTPRequestHandler):
    rules: dict[str, list[dict[str, Any]]] = {}
    log_path: Path

    def do_POST(self) -> None:
        if self.path != PATH:
            self._reply(404, {"error": "not found"})
            return
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or not auth[len("Bearer ") :].strip():
            self._reply(401, {"error": "missing or invalid API key"})
            return
        length = int(self.headers.get("Content-Length") or 0)
        try:
            body = json.loads(self.rfile.read(length))
            instructions = body["questions"]["q"]["instructions"]
            state = body["state"]
        except (ValueError, KeyError, TypeError):
            self._reply(400, {"error": "bad request body"})
            return
        with self.log_path.open("a", encoding="utf-8") as log:
            log.write(json.dumps(body, ensure_ascii=False) + "\n")
            log.flush()
        noul = score(self.rules, instructions, state)
        self._reply(
            200,
            {
                "model": body.get("model"),
                "answers": {"q": {"type": "noul", "noul": noul}},
                "usage": {"requests": 1},
            },
        )

    def _reply(self, status: int, payload: dict[str, Any]) -> None:
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, format: str, *args: Any) -> None:
        pass


def _terminate(signum: int, frame: object) -> None:
    raise SystemExit(0)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rules", required=True, type=Path)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--port-file", required=True, type=Path)
    parser.add_argument("--pid-file", required=True, type=Path)
    args = parser.parse_args(argv)

    Handler.rules = json.loads(args.rules.read_text(encoding="utf-8"))
    Handler.log_path = args.log
    args.log.touch()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    signal.signal(signal.SIGTERM, _terminate)
    args.pid_file.write_text(f"{os.getpid()}\n")
    # Written last: run.sh treats the port file as "ready".
    args.port_file.write_text(f"{server.server_address[1]}\n")
    try:
        server.serve_forever()
    except (SystemExit, KeyboardInterrupt):
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
