"""Example service: answers every request on its port with a small JSON. Only the standard library.

What a service gets from the add-on (environment variables): CA_PORT (listen on 127.0.0.1:<this port>), CA_API_URL and CA_API_TOKEN (the Plugin API of
Car Assistant, see docs/api.md), CA_VEHICLE_ID, CA_DATA_DIR (the only folder it may write to; settings.json lies there).
"""

import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer

DATA = os.environ["CA_DATA_DIR"]


def greeting() -> str:
    with open(os.path.join(DATA, "settings.json"), encoding="utf-8") as fh:
        return json.load(fh).get("greeting", "hello")


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"greeting": greeting(), "path": self.path, "vehicle": os.environ["CA_VEHICLE_ID"]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # the output is kept only while debug is on: say something useful instead
        print("request", self.path)


HTTPServer(("127.0.0.1", int(os.environ["CA_PORT"])), Handler).serve_forever()
