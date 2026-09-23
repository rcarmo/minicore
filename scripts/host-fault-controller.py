#!/usr/bin/env python3
"""Explicit host-owned Unix socket. Only UID10001 and fixed inventory faults.
No TCP listener, no arbitrary Docker request, no secrets returned.
"""

import asyncio
import json
import os
import signal
import socket
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "mcp-service/src"))
from minicore_mcp.host_faults import catalogue, commands, decode, endpoints  # noqa: E402
from minicore_mcp.model import Topology  # noqa: E402

inventory = Topology(ROOT / "inventory/topology.json", ROOT / "runtime/observations.json").inventory
specs = catalogue(inventory)
lock = asyncio.Lock()


async def run(argv):
    # This host service uses no SSH key; subprocess lifecycle only is implemented here.
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    try:
        async with asyncio.timeout(12):

            async def read(stream):
                data = await stream.read(65537)
                if len(data) > 65536:
                    raise ValueError("output_limit")
                return data

            out, err = await asyncio.gather(read(proc.stdout), read(proc.stderr))
            await proc.wait()
            return proc.returncode, out, err
    finally:
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()


def container(node):
    return "minicore-" + next(n["service"] for n in inventory["nodes"] if n["id"] == node) + "-1"


async def inspect(spec):
    if spec["effect"] == "stop":
        code, out, _ = await run(
            ["docker", "inspect", "--format", "{{.State.Running}}", container(spec["target_id"])]
        )
        return [code == 0 and out.strip() == b"true"]
    values = []
    if spec["effect"] == "blackhole":
        code, out, _ = await run(
            [
                "docker",
                "exec",
                container(spec["target_id"]),
                "ip",
                "-j",
                "route",
                "show",
                "exact",
                spec["parameters"]["prefix"],
            ]
        )
        if code:
            raise ValueError("observation_failed")
        return [
            any(r.get("type") == "blackhole" and r.get("metric") == 42760 for r in json.loads(out))
        ]
    for e in endpoints(inventory, spec):
        argv = ["docker", "exec", container(e["node"])]
        code, out, _ = await run(
            argv
            + (
                ["ip", "-j", "link", "show", "dev", e["interface"]]
                if spec["effect"] == "link_down"
                else ["tc", "-j", "qdisc", "show", "dev", e["interface"]]
            )
        )
        if code:
            raise ValueError("observation_failed")
        data = json.loads(out)
        if spec["effect"] == "link_down":
            values.append("UP" in data[0]["flags"])
        else:
            if any(q.get("root") and q.get("kind") not in {"noqueue", "netem"} for q in data):
                raise ValueError("foreign_qdisc")
            values.append(
                any(q.get("handle") == "1234:" and q.get("kind") == "netem" for q in data)
            )
    return values


async def execute(value):
    spec = specs[value["scenario"]]
    action = value["action"]
    effect = spec["effect"]
    before = await inspect(spec)
    desired = action == "reset" if effect in {"stop", "link_down"} else action == "apply"
    cmds = commands(inventory, value["scenario"], action)
    for index, argv in enumerate(cmds):
        if before[index] == desired:
            continue
        code, _, _ = await run(argv)
        if code:
            return {"ok": False, "verified": False, "error_code": "mutation_failed"}
    verified = all(v == desired for v in await inspect(spec))
    return {
        "ok": verified,
        "verified": verified,
        "error_code": None if verified else "verification_failed",
    }


async def client(reader, writer):
    try:
        peer = writer.get_extra_info("socket").getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _, uid, _ = struct.unpack("3i", peer)
        if uid != 10001:
            raise ValueError("denied_identity")
        async with asyncio.timeout(2):
            value = decode(await reader.readline(), inventory)
        if lock.locked():
            result = {"ok": False, "verified": False, "error_code": "mutation_in_progress"}
        else:
            async with lock:
                try:
                    result = await execute(value)
                except Exception:
                    result = {"ok": False, "verified": False, "error_code": "host_execution_failed"}
        writer.write(json.dumps(result).encode() + b"\n")
        await writer.drain()
    except Exception:
        writer.write(b'{"ok":false,"verified":false,"error_code":"denied_operation"}\n')
        try:
            await writer.drain()
        except OSError:
            pass
    finally:
        writer.close()
        await writer.wait_closed()


async def main():
    path = ROOT / "runtime/host-control/fault.sock"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    server = await asyncio.start_unix_server(client, str(path), limit=2048)
    os.chmod(path, 0o660)
    os.chown(path, 10001, 10001)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
