from __future__ import annotations

import argparse
import json
import subprocess
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


DEFAULT_SITE_KEY = "6LdHPmYsAAAAABliA8ARgLuSI8rlBWkZeqxXSKNP"
DEFAULT_CHROME = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")


def page(site_key: str) -> bytes:
    return f"""<!doctype html>
<html>
  <head>
    <meta charset="utf-8">
    <script src="https://www.google.com/recaptcha/enterprise.js?render={site_key}"></script>
  </head>
  <body>
    <div id="status">loading</div>
    <script>
      const status = document.getElementById("status");
      grecaptcha.enterprise.ready(async () => {{
        try {{
          const token = await grecaptcha.enterprise.execute(
            "{site_key}",
            {{ action: "TRADE" }}
          );
          const response = await fetch("/token", {{
            method: "POST",
            headers: {{ "content-type": "application/json" }},
            body: JSON.stringify({{ token }})
          }});
          status.textContent = response.ok ? "ok" : "callback-failed";
        }} catch (error) {{
          status.textContent = `error:${{String(error)}}`;
          await fetch("/error", {{
            method: "POST",
            headers: {{ "content-type": "application/json" }},
            body: JSON.stringify({{ error: String(error) }})
          }});
        }}
      }});
    </script>
  </body>
</html>
""".encode()


class Result:
    def __init__(self) -> None:
        self.event = threading.Event()
        self.token: str | None = None
        self.error: str | None = None


def handler(result: Result, site_key: str) -> type[BaseHTTPRequestHandler]:
    document = page(site_key)

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            if self.path not in {"/", "/index.html"}:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("content-type", "text/html; charset=utf-8")
            self.send_header("content-length", str(len(document)))
            self.end_headers()
            self.wfile.write(document)

        def do_POST(self) -> None:
            length = int(self.headers.get("content-length", "0"))
            try:
                payload = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                payload = {}
            if self.path == "/token":
                result.token = str(payload.get("token") or "")
            elif self.path == "/error":
                result.error = str(payload.get("error") or "unknown browser error")
            else:
                self.send_error(404)
                return
            self.send_response(204)
            self.end_headers()
            result.event.set()

        def log_message(self, _format: str, *_args: object) -> None:
            return

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Test Aark's documented TRADE reCAPTCHA flow.")
    parser.add_argument("--site-key", default=DEFAULT_SITE_KEY)
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--chrome", type=Path, default=DEFAULT_CHROME)
    args = parser.parse_args()

    if not args.chrome.exists():
        raise SystemExit(f"Chrome not found: {args.chrome}")

    result = Result()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), handler(result, args.site_key))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    profile = Path("/tmp/tick-aark-recaptcha-profile")
    started = time.monotonic()
    process = subprocess.Popen(
        [
            str(args.chrome),
            "--headless=new",
            "--disable-gpu",
            "--disable-background-networking",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            f"http://127.0.0.1:{args.port}/",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        completed = result.event.wait(args.timeout)
    finally:
        process.terminate()
        try:
            process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            process.kill()
        server.shutdown()
        server.server_close()

    output = {
        "origin": f"http://127.0.0.1:{args.port}",
        "elapsedMs": round((time.monotonic() - started) * 1000, 1),
        "issued": bool(result.token),
        "token": result.token,
        "error": result.error,
    }
    if not completed or not result.token:
        stderr = process.stderr.read() if process.stderr else ""
        output["browserError"] = stderr[-2000:]
        print(json.dumps(output, indent=2))
        raise SystemExit(1)
    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
