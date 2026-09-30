import http.client
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import unittest

from buraco.web import GameServer


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server = GameServer(("127.0.0.1", 0))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()

    def request(self, method, path, data=None, origin=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port)
        headers = {"Content-Type": "application/json"}
        if origin:
            headers["Origin"] = origin
        connection.request(method, path, None if data is None else json.dumps(data), headers)
        response = connection.getresponse()
        body = response.read()
        content_type = response.getheader("Content-Type")
        status = response.status
        connection.close()
        return status, json.loads(body) if "json" in content_type else body

    def test_start_draw_stale_request_and_confirmed_quit(self):
        code, initial = self.request("GET", "/api/state")
        self.assertEqual(code, 200)
        code, start = self.request("POST", "/api/start", {"version": initial["version"], "seed": "web"})
        self.assertEqual(code, 200)
        code, draw = self.request("POST", "/api/command", {"version": start["version"], "command": "draw stock"})
        self.assertEqual(code, 200)
        code, stale = self.request("POST", "/api/command", {"version": start["version"], "command": "draw stock"})
        self.assertEqual(code, 409)
        self.assertEqual(stale["game"], draw["game"])
        code, _ = self.request("POST", "/api/command", {"version": draw["version"], "command": "quit"})
        self.assertEqual(code, 400)
        code, end = self.request("POST", "/api/command", {"version": draw["version"], "command": "quit", "confirmed": True})
        self.assertEqual(code, 200)
        self.assertTrue(end["game"]["ended"])

    def test_page_assets_and_path_boundary(self):
        for path in ("/", "/style.css", "/app.js"):
            self.assertEqual(self.request("GET", path)[0], 200)
        self.assertEqual(self.request("GET", "/../README.md")[0], 404)
        self.assertEqual(self.request("POST", "/api/start", {"version": 0}, "https://unrelated.example")[0], 403)

    def test_invalid_config_and_active_hand_replacement_rejected(self):
        self.assertEqual(self.request("POST", "/api/start", {"version": 0, "rules": {"no_progress_turn_limit": 0}})[0], 400)
        self.assertEqual(self.request("POST", "/api/start", {"version": 0, "prior_scores": ["wrong", 0]})[0], 400)
        self.assertEqual(self.request("POST", "/api/start", {"version": 0})[0], 200)
        self.assertEqual(self.request("POST", "/api/start", {"version": 1})[0], 400)


class CLITests(unittest.TestCase):
    def test_setup_commands_scoring_and_exit(self):
        script = "\n" * 9 + "cli-test\nstart\ndiscard as\ndraw stock\nhelp\nquit\nyes\n"
        result = subprocess.run([sys.executable, "-m", "buraco"], input=script, text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], timeout=15)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Invalid move: Draw from stock", result.stdout)
        self.assertIn("Final scoring", result.stdout)
        self.assertIn("Morto penalty", result.stdout)
        self.assertIn("Hand stopped by players", result.stdout)

    @unittest.skipUnless(os.name == "nt", "Windows launcher")
    def test_windows_launcher(self):
        script = "\n" * 10 + "start\nquit\nyes\n"
        result = subprocess.run(["cmd", "/c", "launch.cmd", "cli"], input=script, text=True,
                                capture_output=True, cwd=Path(__file__).resolve().parents[1], timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Final scoring", result.stdout)


if __name__ == "__main__":
    unittest.main()
