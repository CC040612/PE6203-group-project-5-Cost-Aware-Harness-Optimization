"""Raw stdio/TCP transport for WSL interop; connects only to Cockpit loopback."""
import os
import socket
import sys
import threading


def main():
    if os.name != "nt":
        raise SystemExit("Run this side using Windows Python")
    import msvcrt
    msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
    msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)
    with socket.create_connection(("127.0.0.1", 58329), timeout=10) as upstream:
        upstream.settimeout(300)

        def send_input():
            try:
                while data := os.read(sys.stdin.fileno(), 65536):
                    upstream.sendall(data)
            except (OSError, ValueError):
                pass
            finally:
                try:
                    upstream.shutdown(socket.SHUT_WR)
                except OSError:
                    pass

        threading.Thread(target=send_input, daemon=True).start()
        while data := upstream.recv(65536):
            view = memoryview(data)
            while view:
                written = os.write(sys.stdout.fileno(), view)
                view = view[written:]


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError):
        print("Windows Cockpit loopback transport closed or unavailable", file=sys.stderr)
        sys.exit(1)
