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
from minicore_mcp.file_io import FileIO  # noqa: E402
from minicore_mcp.host_faults import catalogue, commands, decode, endpoints  # noqa: E402
from minicore_mcp.model import Topology  # noqa: E402

inventory = Topology(ROOT / "inventory/topology.json", ROOT / "runtime/observations.json").inventory
specs = catalogue(inventory)
lock = asyncio.Lock()
files = FileIO(workers=1, capacity=2)
JOURNAL = ROOT / "runtime/host-fault-journal/state.json"


def save_ownership(value):
    JOURNAL.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = JOURNAL.with_suffix(".tmp")
    with temp.open("w") as handle:
        json.dump(value, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.chmod(temp, 0o600)
    os.replace(temp, JOURNAL)
    fd = os.open(JOURNAL.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def ownership():
    if not JOURNAL.exists():
        return None
    if JOURNAL.stat().st_size > 4096:
        raise ValueError("journal_corrupt")
    value = json.loads(JOURNAL.read_text())
    if not isinstance(value, dict) or value.get("scenario") not in specs:
        raise ValueError("journal_corrupt")
    return value


def clear_ownership():
    JOURNAL.unlink()
    fd = os.open(JOURNAL.parent, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


async def run(argv):
    # This host service uses no SSH key; subprocess lifecycle only is implemented here.
    proc = await asyncio.create_subprocess_exec(
        *argv,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        start_new_session=True,
    )
    total = 0
    readers = []
    try:
        async with asyncio.timeout(12):

            async def read(stream):
                nonlocal total
                chunks = []
                while True:
                    data = await stream.read(8192)
                    if not data:
                        return b"".join(chunks)
                    total += len(data)
                    if total > 65536:
                        raise ValueError("output_limit")
                    chunks.append(data)

            readers = [
                asyncio.create_task(read(proc.stdout)),
                asyncio.create_task(read(proc.stderr)),
            ]
            out, err = await asyncio.gather(*readers)
            await proc.wait()
            return proc.returncode, out, err
    finally:
        for task in readers:
            if not task.done():
                task.cancel()
        await asyncio.gather(*readers, return_exceptions=True)
        if proc.returncode is None:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            await proc.wait()


def container(node):
    return "minicore-" + next(n["service"] for n in inventory["nodes"] if n["id"] == node) + "-1"


def netem_matches(options, effect):
    delay = options.get("delay", 0)
    if isinstance(delay, dict):
        delay = delay.get("delay", 0) * 1000000
    loss = options.get("loss-random", options.get("loss", 0))
    if isinstance(loss, dict):
        loss = loss.get("loss", 0) * 100
    return (
        abs(delay - 100000) < 1 and loss == 0
        if effect == "delay"
        else abs(loss - 25) < 0.01 and delay == 0
    )


async def inspect(spec, owned=False):
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
        data = json.loads(out)
        matching = [r for r in data if r.get("type") == "blackhole"]
        if any(r.get("metric") != 1 or str(r.get("protocol")) != "198" for r in matching):
            raise ValueError("foreign_route")
        if matching and not owned:
            raise ValueError("foreign_route")
        return [bool(matching)]
    for e in endpoints(inventory, spec):
        if (
            spec["effect"] in {"delay", "loss"}
            and next(n["kind"] for n in inventory["nodes"] if n["id"] == e["node"]) != "router"
        ):
            continue
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
            roots = [q for q in data if q.get("root") and q.get("kind") != "noqueue"]
            if roots and (
                not owned
                or any(q.get("handle") != "1234:" or q.get("kind") != "netem" for q in roots)
            ):
                raise ValueError("foreign_qdisc")
            for q in roots:
                opts = q.get("options", {})
                if not netem_matches(opts, spec["effect"]):
                    raise ValueError("foreign_qdisc")
            values.append(bool(roots))
    return values


async def execute(value):
    spec = specs[value["scenario"]]
    action = value["action"]
    effect = spec["effect"]
    journal = await files.run(ownership)
    if action == "reset" and (journal is None or journal["scenario"] != value["scenario"]):
        return {"ok": True, "verified": True, "error_code": None}
    if action == "apply" and journal and journal["scenario"] != value["scenario"]:
        return {"ok": False, "verified": False, "error_code": "fault_conflict"}
    before = await inspect(spec, owned=journal is not None)
    desired = action == "reset" if effect in {"stop", "link_down"} else action == "apply"
    if action == "apply" and journal is None:
        baseline = all(before) if effect in {"stop", "link_down"} else not any(before)
        if not baseline:
            return {"ok": False, "verified": False, "error_code": "baseline_unverified"}
        await files.run(save_ownership, {"scenario": value["scenario"], "phase": "applying"})
    cmds = commands(inventory, value["scenario"], action)
    for index, argv in enumerate(cmds):
        if before[index] == desired:
            continue
        code, _, _ = await run(argv)
        if code:
            return {"ok": False, "verified": False, "error_code": "mutation_failed"}
    verified = all(v == desired for v in await inspect(spec, owned=True))
    if verified:
        if action == "reset":
            await files.run(clear_ownership)
        else:
            await files.run(save_ownership, {"scenario": value["scenario"], "phase": "active"})
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
                except Exception as exc:
                    import traceback

                    traceback.print_exc()
                    code = (
                        str(exc)
                        if isinstance(exc, ValueError)
                        and str(exc)
                        in {
                            "foreign_qdisc",
                            "foreign_route",
                            "journal_corrupt",
                            "observation_failed",
                            "output_limit",
                        }
                        else "host_execution_failed"
                    )
                    result = {"ok": False, "verified": False, "error_code": code}
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

    def prepare():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.unlink(missing_ok=True)

    await files.run(prepare)
    server = await asyncio.start_unix_server(client, str(path), limit=2048)
    await files.run(os.chmod, path, 0o660)
    # Provisioned setgid directory supplies GID 10001 without a root daemon.
    if (await files.run(path.stat)).st_gid != 10001:
        raise RuntimeError("Provision host-control directory with group 10001")
    try:
        async with server:
            await server.serve_forever()
    finally:
        await files.close()


if __name__ == "__main__":
    asyncio.run(main())
