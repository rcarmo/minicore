#!/usr/bin/env python3
"""Test-only fake SSH executable. Real subprocess IO, no network or real credentials."""

import json
import os
import subprocess
import sys
import time
from pathlib import Path

root = Path(os.environ["SSH_FIXTURE_ROOT"])
mode = (root / "mode").read_text()
request = json.loads(sys.stdin.read())
with (root / "events").open("a") as f:
    f.write(
        json.dumps(
            {
                "event": "start",
                "pid": os.getpid(),
                "node": sys.argv[-2],
                "at": time.monotonic(),
                "argv": sys.argv[1:],
            }
        )
        + "\n"
    )
if mode in {"hang", "orphan"}:
    child = subprocess.Popen([sys.executable, "-c", "import time;time.sleep(60)"])
    with (root / "pids").open("a") as f:
        f.write(f"{os.getpid()} {child.pid}\n")
    if mode == "orphan":
        sys.exit(0)
    time.sleep(60)
if mode == "cap":
    sys.stdout.write("x" * 70000)
    sys.exit(0)
if mode == "combined":
    sys.stdout.write("x" * 40000)
    sys.stdout.flush()
    sys.stderr.write("y" * 40000)
    sys.exit(0)
errors = {
    "host": "Host key verification failed",
    "auth": "Permission denied (publickey)",
    "connect": "Connection timed out",
    "absent": "No route to host",
}
if mode in errors:
    sys.stderr.write(errors[mode])
    sys.exit(255)
if mode == "malformed":
    print("{")
    sys.exit(0)
if mode == "concurrency":
    time.sleep(0.1)
result = {
    "status": "ok",
    "data": {"request": request},
    "raw_evidence": "{}",
    "truncated": False,
    "duration_ms": 1,
    "error_code": None,
}
if mode == "shape":
    result["data"] = "pretend healthy"
if mode == "false_error":
    result.update(status="error", error_code=None)
if mode == "fields":
    result["secret"] = "must not pass"
with (root / "events").open("a") as f:
    f.write(json.dumps({"event": "finish", "pid": os.getpid(), "at": time.monotonic()}) + "\n")
print(json.dumps(result))
