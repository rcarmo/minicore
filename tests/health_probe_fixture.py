"""Isolated image probe fixture: no production listener or network access."""

import json
import socket
import subprocess
import sys
import threading
import time

mode, raw_command = sys.argv[1:]
command = json.loads(raw_command)
listener = None
requests = []
workers = []
stop = threading.Event()
if mode != "unavailable":
    listener = socket.socket()
    listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    listener.bind(("127.0.0.1", 9000))
    listener.listen(1)
    listener.settimeout(5)

    def serve():
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(3)
            requests.append(connection.recv(2048).split(b"\r\n", 1)[0].decode())
            if mode == "stalled":
                stop.wait(5)
            else:
                status = "200 OK" if mode == "healthy" else "503 Service Unavailable"
                connection.sendall(
                    f"HTTP/1.1 {status}\r\nContent-Length: 0\r\nConnection: close\r\n\r\n".encode()
                )

    worker = threading.Thread(target=serve, daemon=True)
    workers.append(worker)
    worker.start()

start = time.monotonic()
try:
    probe = subprocess.run(command, capture_output=True, timeout=5)
    result = {"exit_code": probe.returncode, "elapsed": time.monotonic() - start}
finally:
    stop.set()
    for worker in workers:
        worker.join(timeout=6)
    if listener:
        listener.close()
result["requests"] = requests
print(json.dumps(result))
