"""Loopback-only, dependency-free HTTP frontend for the shared engine."""

import argparse
from dataclasses import asdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import threading
from urllib.parse import urlparse
import webbrowser

from .config import Rules
from .engine import Game, RuleError

STATIC = Path(__file__).parent / "static"


class GameServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address):
        super().__init__(address, Handler)
        self.game = None
        self.lock = threading.Lock()
        self.version = 0

    def snapshot(self):
        return {"version": self.version, "game": self.game.view() if self.game else None,
                "defaults": asdict(Rules())}


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def reply(self, status, body, content_type="application/json; charset=utf-8"):
        if not isinstance(body, bytes):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def valid_host(self):
        host = self.headers.get("Host", "")
        port = self.server.server_port
        return host in (f"127.0.0.1:{port}", f"localhost:{port}")

    def do_GET(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Use the local server address."})
        path = urlparse(self.path).path
        if path == "/api/state":
            with self.server.lock:
                return self.reply(200, self.server.snapshot())
        files = {"/": ("index.html", "text/html"), "/app.js": ("app.js", "text/javascript"),
                 "/style.css": ("style.css", "text/css")}
        if path not in files:
            return self.reply(404, {"error": "Not found."})
        name, mime = files[path]
        self.reply(200, (STATIC / name).read_bytes(), mime + "; charset=utf-8")

    def do_POST(self):
        if not self.valid_host():
            return self.reply(403, {"error": "Use the local server address."})
        origin = self.headers.get("Origin")
        if origin is not None and origin != "http://" + self.headers.get("Host", ""):
            return self.reply(403, {"error": "Requests must come from this game page."})
        if self.headers.get("Content-Type", "").split(";")[0] != "application/json":
            return self.reply(415, {"error": "JSON required."})
        try:
            length = int(self.headers.get("Content-Length", 0))
            if not 0 < length <= 16384:
                raise ValueError("Invalid request size.")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object.")
            with self.server.lock:
                if data.get("version") != self.server.version:
                    return self.reply(409, {"error": "The table changed. Review the current turn and try again.", **self.server.snapshot()})
                if self.path == "/api/start":
                    if self.server.game and not self.server.game.ended:
                        raise RuleError("Finish or quit the current hand before starting another.")
                    settings = data.get("rules", {})
                    if not isinstance(settings, dict):
                        raise ValueError("Invalid game options.")
                    seed = data.get("seed")
                    if seed is not None and not isinstance(seed, str):
                        raise ValueError("Seed must be text.")
                    candidate = Game(Rules(**settings), data.get("prior_scores", [0, 0]), seed or None)
                    self.server.game = candidate
                    message = "Hand started. Player 1 draws first."
                elif self.path == "/api/command":
                    if self.server.game is None:
                        raise RuleError("Start a hand first.")
                    command = data.get("command")
                    if not isinstance(command, str):
                        raise ValueError("Command must be text.")
                    if command.strip().lower() == "quit" and data.get("confirmed") is not True:
                        raise RuleError("Confirm before ending the hand.")
                    message = self.server.game.execute(command)
                else:
                    return self.reply(404, {"error": "Not found."})
                self.server.version += 1
                self.reply(200, {"message": message, **self.server.snapshot()})
        except (ValueError, TypeError) as error:
            self.reply(400, {"error": str(error)})


def main():
    parser = argparse.ArgumentParser(description="Play Buraco in your browser using the local Python engine.")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open the browser")
    args = parser.parse_args()
    try:
        server = GameServer(("127.0.0.1", args.port))
    except OSError as error:
        parser.exit(1, f"Could not start the local server: {error}\nTry a different --port.\n")
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"Buraco: {url}\nKeep this terminal open. Press Ctrl+C to stop the server.")
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
