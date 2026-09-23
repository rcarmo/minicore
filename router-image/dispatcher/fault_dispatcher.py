#!/usr/bin/python3
"""Root forced command with exactly three fixed data-plane effects. No caller parameters."""

import json
import os
import signal
import subprocess
import sys
from pathlib import Path

SCENARIOS = {
    "core-link-failure": ("p1", "to-p2"),
    "customer-bgp-failure": ("ce1", "to-pe1"),
    "data-path-degradation": ("ce1", "to-host1"),
}


def compile_request(data, node):
    if (
        not isinstance(data, dict)
        or set(data) != {"operation", "scenario", "action"}
        or data["operation"] != "fault"
    ):
        raise ValueError("denied_operation")
    scenario = data["scenario"]
    action = data["action"]
    if (
        not isinstance(scenario, str)
        or scenario not in SCENARIOS
        or action not in ("apply", "reset")
    ):
        raise ValueError("denied_operation")
    target, interface = SCENARIOS[scenario]
    if node != target:
        raise ValueError("denied_target")
    if scenario == "data-path-degradation":
        command = (
            [
                "/sbin/tc",
                "qdisc",
                "replace",
                "dev",
                interface,
                "root",
                "handle",
                "1234:",
                "netem",
                "delay",
                "100ms",
                "loss",
                "10%",
            ]
            if action == "apply"
            else ["/sbin/tc", "qdisc", "del", "dev", interface, "root", "handle", "1234:"]
        )
    else:
        command = [
            "/sbin/ip",
            "link",
            "set",
            "dev",
            interface,
            "down" if action == "apply" else "up",
        ]
    return command


def run(cmd):
    p = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=5,
        env={"PATH": "/usr/bin:/bin:/sbin", "LC_ALL": "C"},
    )
    if len(p.stdout) + len(p.stderr) > 8192:
        raise ValueError("output_limit")
    return p


def main():
    result = {
        "status": "error",
        "data": None,
        "error_code": "denied_operation",
        "raw_evidence": "",
        "duration_ms": 0,
        "truncated": False,
    }
    try:
        signal.alarm(10)
        if os.environ.get("SSH_ORIGINAL_COMMAND") != "minicore-fault":
            raise ValueError()
        raw = sys.stdin.buffer.read(4097)
        if len(raw) > 4096:
            raise ValueError()
        data = json.loads(raw)
        node = json.loads(Path("/etc/minicore/node.json").read_text())["node_id"]
        cmd = compile_request(data, node)
        interface = SCENARIOS[data["scenario"]][1]
        if data["scenario"] == "data-path-degradation":
            existing = run(["/sbin/tc", "-j", "qdisc", "show", "dev", interface])
            qdiscs = json.loads(existing.stdout)
            ours = any(q.get("handle") == "1234:" for q in qdiscs)
            if data["action"] == "apply" and any(
                q.get("root")
                and q.get("kind") not in ("noqueue", "pfifo_fast")
                and q.get("handle") != "1234:"
                for q in qdiscs
            ):
                raise ValueError("foreign_qdisc")
            if data["action"] == "reset" and not ours:
                p = None
            else:
                p = run(cmd)
            verify = run(["/sbin/tc", "-j", "qdisc", "show", "dev", interface])
            after = json.loads(verify.stdout)
            verified = any(
                q.get("kind") == "netem" and q.get("handle") == "1234:" for q in after
            ) == (data["action"] == "apply")
        else:
            p = run(cmd)
            verify = run(["/sbin/ip", "-j", "link", "show", "dev", interface])
            after = json.loads(verify.stdout)
            verified = ("UP" in after[0]["flags"]) == (data["action"] == "reset")
        if p and p.returncode:
            raise ValueError("mutation_failed")
        if not verified:
            raise ValueError("verification_failed")
        result.update(
            status="ok",
            error_code=None,
            data={"ok": True, "verified": True},
            raw_evidence=verify.stdout,
        )
    except (ValueError, KeyError, TypeError, OSError, subprocess.TimeoutExpired):
        result["error_code"] = "mutation_failed"
    print(json.dumps(result))


if __name__ == "__main__":
    main()
