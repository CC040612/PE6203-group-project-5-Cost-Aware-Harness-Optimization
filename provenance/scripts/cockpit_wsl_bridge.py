"""Local-only raw TCP bridge using Windows Python through WSL interop.

Without --command, read the model catalog once and exit; never generate text.
The transport does not alter requests, choose models, retry, or record secrets.
"""
import argparse
import json
import os
import platform
import socket
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WINDOWS_PYTHON = "/mnt/c/Users/Lenovo/.cache/codex-runtimes/codex-primary-runtime/dependencies/python/python.exe"
ADDRESS = ("127.0.0.1", 58429)


class Transport(socketserver.BaseRequestHandler):
    def handle(self):
        script = subprocess.check_output(["wslpath", "-w", str(ROOT / "scripts" / "cockpit_windows_pipe.py")], text=True).strip()
        process = subprocess.Popen([WINDOWS_PYTHON, "-u", script], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)

        def send_input():
            try:
                while data := self.request.recv(65536):
                    process.stdin.write(data)
                    process.stdin.flush()
            except (OSError, ValueError):
                pass
            finally:
                try:
                    process.stdin.close()
                except OSError:
                    pass

        threading.Thread(target=send_input, daemon=True).start()
        try:
            while data := os.read(process.stdout.fileno(), 65536):
                self.request.sendall(data)
        except OSError:
            pass
        finally:
            try:
                self.request.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


class Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def main():
    if platform.system() != "Linux" or not Path(WINDOWS_PYTHON).is_file():
        raise SystemExit("This bridge requires the configured WSL and Windows Python")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    with Server(ADDRESS, Transport) as server:
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            if args.command:
                raise SystemExit(subprocess.call(args.command))
            settings = dict(line.split("=", 1) for line in (ROOT / "config" / "cockpit-local.env").read_text().splitlines() if line and not line.startswith("#") and "=" in line)
            request = urllib.request.Request("http://127.0.0.1:58429/v1/models", headers={"Authorization": "Bearer " + settings["OPENAI_API_KEY"]})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            started = time.monotonic()
            with opener.open(request, timeout=30) as response:
                catalog = json.load(response)
                status = response.status
            models = [m.get("id", m.get("slug")) for m in catalog.get("data", catalog.get("models", []))]
            assert "gpt-6.1-sol" in models
            report = {"passed": True, "timestamp_utc": datetime.now(timezone.utc).isoformat(), "http_status": status,
                      "execution_platform": platform.system(), "transport": "WSL loopback -> Windows interop stdio -> Windows loopback",
                      "wsl_base_url": "http://127.0.0.1:58429/v1", "windows_base_url": "http://127.0.0.1:58329/v1",
                      "models": models, "catalog_elapsed_sec": round(time.monotonic()-started, 3), "generation_requests": 0,
                      "streaming_generation_verified": False, "harness_compatibility_verified": False}
            (ROOT / "config" / "cockpit-wsl-connection.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            server.shutdown()


if __name__ == "__main__":
    main()
