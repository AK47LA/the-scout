"""Headless Chrome over the DevTools protocol, standard library only: open a page, seek its animations, take frames.

  with Chrome(width=1080, height=1350) as c:
      c.open("file:///.../scene.html")
      for i in range(frames):
          jpeg_bytes = c.frame(i / fps)
The page's CSS animations are paused and set to the exact time before each frame, so output is frame-accurate
and does not depend on how fast the machine renders.
"""
import base64, json, os, shutil, signal, socket, struct, subprocess, tempfile, time, urllib.request

import capture

SEEK_JS = """(t => { for (const a of document.getAnimations()) { a.pause(); a.currentTime = t * 1000; }
  const p = window.onSeek ? window.onSeek(t) : null;
  return Promise.resolve(p).then(() => new Promise(r => requestAnimationFrame(() => r(1)))); })"""


class _WS:
    """Just enough of RFC 6455 for one client talking to Chrome."""

    def __init__(self, url):
        host, rest = url.split("://", 1)[1].split("/", 1)
        h, p = host.split(":")
        self.s = socket.create_connection((h, int(p)), timeout=120)
        key = base64.b64encode(os.urandom(16)).decode()
        self.s.sendall(f"GET /{rest} HTTP/1.1\r\nHost: {host}\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                       f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n".encode())
        self.buf = b""
        while b"\r\n\r\n" not in self.buf:
            self.buf += self.s.recv(4096)
        head, self.buf = self.buf.split(b"\r\n\r\n", 1)
        if b" 101 " not in head.split(b"\r\n")[0]:
            raise ConnectionError(head[:200])

    def _exact(self, n):
        while len(self.buf) < n:
            chunk = self.s.recv(max(65536, n - len(self.buf)))
            if not chunk:
                raise ConnectionError("chrome closed the socket")
            self.buf += chunk
        out, self.buf = self.buf[:n], self.buf[n:]
        return out

    def send(self, text):
        data = text.encode()
        n = len(data)
        head = bytes([0x81]) + (bytes([0x80 | n]) if n < 126 else bytes([0x80 | 126]) + struct.pack(">H", n) if n < 65536
                                else bytes([0x80 | 127]) + struct.pack(">Q", n))
        mask = os.urandom(4)
        self.s.sendall(head + mask + bytes(b ^ mask[i % 4] for i, b in enumerate(data)))

    def recv(self):
        parts = []
        while True:
            b0, b1 = self._exact(2)
            n = b1 & 0x7F
            n = struct.unpack(">H", self._exact(2))[0] if n == 126 else struct.unpack(">Q", self._exact(8))[0] if n == 127 else n
            payload = self._exact(n)
            op = b0 & 0x0F
            if op == 0x9:  # ping
                self.s.sendall(bytes([0x8A, 0x80 | len(payload)]) + b"\0\0\0\0" + payload)
                continue
            if op == 0x8:
                raise ConnectionError("chrome closed the session")
            parts.append(payload)
            if b0 & 0x80:
                return b"".join(parts).decode()


class Chrome:
    def __init__(self, width=1080, height=1350, chrome=None):
        self.w, self.h = width, height
        self.bin = chrome or capture.find_chrome()
        if not self.bin:
            raise RuntimeError("Chrome not found; set SCOUT_CHROME")
        self.n = 0

    def __enter__(self):
        self.prof = tempfile.mkdtemp(prefix="scout-cdp-")
        with socket.socket() as s:
            s.bind(("127.0.0.1", 0))
            port = s.getsockname()[1]
        self.proc = subprocess.Popen([self.bin, "--headless=new", f"--remote-debugging-port={port}", f"--user-data-dir={self.prof}",
                                      f"--window-size={self.w},{self.h}", "--hide-scrollbars", "--force-device-scale-factor=1",
                                      "--mute-audio", "--no-first-run", "--no-default-browser-check", "--allow-file-access-from-files",
                                      "about:blank"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        base = f"http://127.0.0.1:{port}"
        for _ in range(100):
            try:
                urllib.request.urlopen(base + "/json/version", timeout=2).read()
                break
            except Exception:
                time.sleep(0.1)
        tab = json.load(urllib.request.urlopen(urllib.request.Request(base + "/json/new?about:blank", method="PUT"), timeout=10))
        self.ws = _WS(tab["webSocketDebuggerUrl"])
        self.call("Emulation.setDeviceMetricsOverride", width=self.w, height=self.h, deviceScaleFactor=1, mobile=False)
        self.call("Page.enable")
        return self

    def __exit__(self, *exc):
        try:
            os.killpg(self.proc.pid, signal.SIGKILL)
        except Exception:
            pass
        shutil.rmtree(self.prof, ignore_errors=True)

    def call(self, method, **params):
        self.n += 1
        self.ws.send(json.dumps({"id": self.n, "method": method, "params": params}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                return msg.get("result", {})

    def js(self, expr, wait=True):
        r = self.call("Runtime.evaluate", expression=expr, awaitPromise=wait, returnByValue=True)
        return (r.get("result") or {}).get("value")

    def open(self, url, settle=0.3):
        self.call("Page.navigate", url=url)
        for _ in range(200):
            if self.js("document.readyState", wait=False) == "complete":
                break
            time.sleep(0.05)
        self.js("document.fonts.ready.then(() => Promise.all([...document.images].map(i => i.complete ? 1 : new Promise(r => { i.onload = i.onerror = r; }))))")
        time.sleep(settle)

    def frame(self, t, quality=92):
        self.js(f"{SEEK_JS}({t:.4f})")
        r = self.call("Page.captureScreenshot", format="jpeg", quality=quality, captureBeyondViewport=False)
        return base64.b64decode(r["data"])
