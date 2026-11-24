"""A very small Chrome DevTools client (standard library only) for the screenshots that need a click or a photo upload first.

``make_screenshots.py`` takes plain pictures of pages with ``chrome --screenshot``. A picture of the odometer plate turned over, or of the fill-up
form after a receipt was scanned, needs a person to tap and to pick a photo: this starts the same headless Chrome with a debugging port, opens the
page, lets a script do what the person does, and takes the picture.

  with Browser() as b:
      b.open(url, width=500, height=900, scale=2)
      b.run("document.querySelector('button').click()")
      b.wait_for("document.querySelector('.done')")
      b.shot(path, clip=(0, 0, 500, 300))
"""

from __future__ import annotations

import base64
import json
import os
import socket
import shutil
import struct
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path


def find_chrome() -> str | None:
    """Google Chrome or Chromium: ``CHROME`` (a path), the Mac application, or a program of that name on the path; None when there is none."""
    candidates = [os.environ.get("CHROME") or "", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"]
    candidates += [shutil.which(name) or "" for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "chrome")]
    return next((c for c in candidates if c and Path(c).exists()), None)


CHROME = find_chrome() or "chrome"


class _Socket:
    """The client side of a WebSocket: the handshake, masked text frames out, text frames in."""

    def __init__(self, url: str):
        host, _, rest = url.removeprefix("ws://").partition("/")
        name, _, port = host.partition(":")
        self.sock = socket.create_connection((name, int(port)), timeout=60)
        key = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall(
            (
                f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n"
            ).encode()
        )
        reply = b""
        while b"\r\n\r\n" not in reply:
            reply += self.sock.recv(4096)
        if b" 101 " not in reply.split(b"\r\n", 1)[0]:
            raise RuntimeError("the browser refused the connection")
        self.buffer = reply.split(b"\r\n\r\n", 1)[1]

    def _read(self, n: int) -> bytes:
        while len(self.buffer) < n:
            chunk = self.sock.recv(1 << 20)
            if not chunk:
                raise RuntimeError("the browser closed the connection")
            self.buffer += chunk
        data, self.buffer = self.buffer[:n], self.buffer[n:]
        return data

    def send(self, text: str) -> None:
        payload = text.encode()
        head = bytearray([0x81])
        n = len(payload)
        if n < 126:
            head.append(0x80 | n)
        elif n < 1 << 16:
            head += bytes([0x80 | 126]) + struct.pack(">H", n)
        else:
            head += bytes([0x80 | 127]) + struct.pack(">Q", n)
        mask = os.urandom(4)
        self.sock.sendall(bytes(head) + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(payload)))

    def recv(self) -> str:
        message = b""
        while True:
            b0, b1 = self._read(2)
            n = b1 & 0x7F
            if n == 126:
                (n,) = struct.unpack(">H", self._read(2))
            elif n == 127:
                (n,) = struct.unpack(">Q", self._read(8))
            data = self._read(n)
            opcode = b0 & 0x0F
            if opcode == 0x8:
                raise RuntimeError("the browser closed the connection")
            if opcode in (0x1, 0x0):
                message += data
                if b0 & 0x80:
                    return message.decode()


class Browser:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="ca-chrome-")
        self.port = _free_port()
        self.proc = subprocess.Popen(
            [
                CHROME,
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--no-first-run",
                *(["--no-sandbox"] if hasattr(os, "geteuid") and os.geteuid() == 0 else []),  # a root user (a container) cannot use the sandbox
                f"--remote-debugging-port={self.port}",
                f"--user-data-dir={self.tmp.name}",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        self.next_id = 0
        end = time.time() + 30
        target = None
        while time.time() < end and target is None:
            try:
                pages = json.load(urllib.request.urlopen(f"http://127.0.0.1:{self.port}/json", timeout=2))
                target = next((p for p in pages if p.get("type") == "page"), None)
            except Exception:
                time.sleep(0.3)
        if target is None:
            raise RuntimeError("Chrome did not start")
        self.ws = _Socket(target["webSocketDebuggerUrl"])
        self.call("Page.enable")

    def __enter__(self) -> Browser:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.tmp.cleanup()

    def call(self, method: str, **params):
        self.next_id += 1
        self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        while True:
            reply = json.loads(self.ws.recv())
            if reply.get("id") == self.next_id:
                if "error" in reply:
                    raise RuntimeError(f"{method}: {reply['error']}")
                return reply.get("result", {})

    def open(self, url: str, width: int, height: int, scale: int = 1, settle: float = 2.5) -> None:
        self.call("Emulation.setDeviceMetricsOverride", width=width, height=height, deviceScaleFactor=scale, mobile=False)
        self.call("Page.navigate", url=url)
        time.sleep(0.2)  # the old page is gone
        end = time.time() + 20
        while time.time() < end and self.run("document.readyState") != "complete":
            time.sleep(0.1)
        time.sleep(settle)  # the scripts and the first animations

    def run(self, js: str):
        """Run a script in the page (a promise is awaited); the value it returns comes back."""
        res = self.call("Runtime.evaluate", expression=js, awaitPromise=True, returnByValue=True)
        if "exceptionDetails" in res:
            raise RuntimeError(res["exceptionDetails"].get("exception", {}).get("description", "script failed"))
        return res["result"].get("value")

    def wait_for(self, js: str, seconds: float = 40) -> None:
        end = time.time() + seconds
        while time.time() < end:
            if self.run(f"!!({js})"):
                return
            time.sleep(0.4)
        raise RuntimeError(f"timed out waiting for: {js}")

    def shot(self, path: Path, clip: tuple[float, float, float, float] | None = None, scale: float | None = None) -> None:
        """The visible page as PNG; ``clip`` is (x, y, width, height) in page pixels."""
        params: dict = {"format": "png"}
        if clip:
            params["clip"] = {"x": clip[0], "y": clip[1], "width": clip[2], "height": clip[3], "scale": scale or 1}
        data = self.call("Page.captureScreenshot", **params)["data"]
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_bytes(base64.b64decode(data))


def upload_script(selector: str, data: bytes, name: str, mime: str) -> str:
    """A script that puts a file into a file input the way a person picking a photo does (the page's own change handler runs)."""
    b64 = base64.b64encode(data).decode()
    return (
        "(function(){var b=atob('" + b64 + "'),a=new Uint8Array(b.length);for(var i=0;i<b.length;i++){a[i]=b.charCodeAt(i);}"
        "var dt=new DataTransfer();dt.items.add(new File([a],'" + name + "',{type:'" + mime + "'}));"
        "var el=document.querySelector('" + selector + "');el.files=dt.files;el.dispatchEvent(new Event('change',{bubbles:true}));})()"
    )


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]
