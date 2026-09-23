#!/usr/bin/python3
"""Fixed SSH command dispatcher. No caller-controlled shell or executable path."""

import ipaddress
import json
import os
import re
import selectors
import signal
import subprocess
import sys
import time
from pathlib import Path

LIMIT = 48 * 1024
ALLOWED = {
    "get_routes": {"operation", "prefix"},
    "get_interfaces": {"operation", "interface"},
    "get_neighbors": {"operation", "protocol"},
    "ping": {"operation", "destination", "count"},
}


def decode_request(payload):
    if len(payload) > 4096:
        raise ValueError("invalid_arguments")
    data = json.loads(payload)
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("operation"), str)
        or data["operation"] not in ALLOWED
    ):
        raise ValueError("denied_operation")
    if set(data) - ALLOWED[data["operation"]]:
        raise ValueError("invalid_arguments")
    return data


def command_for(request, inventory):
    operation = request["operation"]
    if operation == "get_routes":
        prefix = request.get("prefix")
        if prefix is not None:
            if not isinstance(prefix, str):
                raise ValueError("invalid_prefix")
            ipaddress.IPv4Network(prefix, strict=True)
        return [
            "/usr/bin/vtysh",
            "-c",
            "show ip route" + (" " + prefix if prefix else "") + " json",
        ]
    if operation == "get_interfaces":
        interface = request.get("interface")
        if interface is not None and interface not in inventory["interfaces"]:
            raise ValueError("unknown_interface")
        return ["/sbin/ip", "-j", "-s", "address", "show"] + (
            ["dev", interface] if interface else []
        )
    if operation == "get_neighbors":
        protocol = request.get("protocol")
        if protocol not in {"bgp", "ospf"}:
            raise ValueError("invalid_protocol")
        if protocol not in inventory.get("protocols", []):
            raise ValueError("protocol_not_enabled")
        return [
            "/usr/bin/vtysh",
            "-c",
            "show bgp summary json" if protocol == "bgp" else "show ip ospf neighbor json",
        ]
    if operation == "ping":
        destination = request.get("destination")
        count = request.get("count", 3)
        if destination not in inventory["destinations"]:
            raise ValueError("denied_destination")
        if type(count) is not int or not 1 <= count <= 5:
            raise ValueError("invalid_count")
        return ["/bin/ping", "-n", "-c", str(count), "-W", "1", destination]
    raise ValueError("denied_operation")


def run_bounded(argv, deadline=10, limit=LIMIT):
    started = time.monotonic()
    out = bytearray()
    err = bytearray()
    error = None
    proc = subprocess.Popen(
        argv,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        start_new_session=True,
        env={"PATH": "/usr/bin:/bin:/sbin", "LC_ALL": "C"},
    )
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ, out)
    selector.register(proc.stderr, selectors.EVENT_READ, err)
    try:
        while selector.get_map():
            if time.monotonic() - started >= deadline:
                error = "execution_timeout"
                break
            for key, _ in selector.select(0.05):
                data = os.read(key.fileobj.fileno(), 8192)
                if not data:
                    selector.unregister(key.fileobj)
                    continue
                remaining = limit - len(out) - len(err)
                key.data.extend(data[:remaining])
                if len(data) > remaining:
                    error = "output_limit"
                    break
            if error:
                break
    finally:
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        proc.wait()
        selector.close()
        proc.stdout.close()
        proc.stderr.close()
    return {
        "stdout": out.decode(errors="replace"),
        "stderr": err.decode(errors="replace"),
        "exit_code": proc.returncode,
        "error_code": error,
        "duration_ms": round((time.monotonic() - started) * 1000),
    }


def normalise(operation, output):
    if operation != "ping":
        data = json.loads(output)
        if not isinstance(data, (dict, list)):
            raise ValueError("parse_failure")
        return data
    match = re.search(
        r"(\d+) packets transmitted, (\d+) (?:packets )?received, ([\d.]+)% packet loss", output
    )
    if not match:
        raise ValueError("parse_failure")
    rtt = re.search(r"(?:round-trip|rtt) [^=]+= ([\d.]+)/([\d.]+)/([\d.]+)", output)
    return {
        "sent": int(match[1]),
        "received": int(match[2]),
        "loss_percent": float(match[3]),
        "rtt_ms": {"min": float(rtt[1]), "avg": float(rtt[2]), "max": float(rtt[3])}
        if rtt
        else None,
    }


def main():
    result = {
        "status": "error",
        "error_code": "invalid_arguments",
        "data": None,
        "raw_evidence": "",
        "truncated": False,
        "duration_ms": 0,
    }
    try:
        signal.alarm(12)
        if os.environ.get("SSH_ORIGINAL_COMMAND") != "minicore-dispatch":
            raise ValueError("denied_operation")
        request = decode_request(sys.stdin.buffer.read(4097))
        inventory = json.loads(Path("/etc/minicore/node.json").read_text())
        cmd = command_for(request, inventory)
        execution = run_bounded(cmd)
        error = execution["error_code"]
        if (
            not error
            and execution["exit_code"] != 0
            and not (request["operation"] == "ping" and execution["exit_code"] == 1)
        ):
            error = "command_failed"
        data = None
        if not error:
            try:
                data = normalise(request["operation"], execution["stdout"])
                if request["operation"] == "get_interfaces":
                    data = [item for item in data if item.get("ifname") in inventory["interfaces"]]
                    execution["stdout"] = json.dumps(data)
            except (ValueError, TypeError):
                error = "parse_failure"
        result.update(
            status="error" if error else "ok",
            error_code=error,
            data=data,
            raw_evidence=execution["stdout"],
            truncated=error == "output_limit",
            duration_ms=execution["duration_ms"],
        )
    except (ValueError, TypeError, KeyError) as exc:
        code = str(exc)
        if code in {
            "protocol_not_enabled",
            "unknown_interface",
            "denied_operation",
            "invalid_protocol",
            "denied_destination",
            "invalid_count",
        }:
            result["error_code"] = code
    except OSError:
        result["error_code"] = "node_unavailable"
    encoded = json.dumps(result)
    if len(encoded.encode()) > 65536:
        encoded = json.dumps(
            {
                "status": "error",
                "error_code": "output_limit",
                "data": None,
                "raw_evidence": "",
                "truncated": True,
                "duration_ms": result["duration_ms"],
            }
        )
    print(encoded)


if __name__ == "__main__":
    main()
