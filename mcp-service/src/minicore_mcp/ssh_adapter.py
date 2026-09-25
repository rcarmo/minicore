"""Inventory-only forced-command SSH. Bounded IO/deadlines, host-key pinning and cleanup."""

import asyncio
import json
import os
import signal
import time
from pathlib import Path

from .file_io import FileIO


class SSHAdapter:
    def __init__(self, topology, directory: Path, *, fault=False):
        self.files = FileIO(workers=1, capacity=32)
        self.topology = topology
        self.key = directory / ("fault" if fault else "diagnostic")
        self.identity = "root" if fault else "diagnostic"
        self.command = "minicore-fault" if fault else "minicore-dispatch"
        self.known_hosts = directory / "known_hosts"
        self.global_slots = asyncio.Semaphore(8)
        self.node_slots = {n: asyncio.Semaphore(2) for n in topology.nodes}

    async def execute(self, node, request):
        started = time.monotonic()
        result = {
            "status": "unavailable",
            "error_code": None,
            "data": None,
            "raw_evidence": "",
            "truncated": False,
            "duration_ms": 0,
        }
        info = self.topology.nodes.get(node)
        if not info or not info.get("management_address"):
            return result | {"error_code": "unsupported_node"}
        try:
            ready = await self.files.run(lambda: self.key.exists() and self.known_hosts.exists())
        except OSError:
            return result | {"error_code": "file_io_busy"}
        if not ready:
            return result | {"error_code": "backend_not_configured"}
        proc = None
        readers = []
        total_bytes = 0

        async def read(stream):
            nonlocal total_bytes
            chunks = bytearray()
            while True:
                block = await stream.read(8192)
                if not block:
                    break
                total_bytes += len(block)
                if total_bytes > 65536:
                    raise OverflowError()
                chunks.extend(block)
            return chunks.decode(errors="replace")

        try:
            async with asyncio.timeout(15):
                async with self.global_slots, self.node_slots[node]:
                    argv = [
                        "ssh",
                        "-T",
                        "-i",
                        str(self.key),
                        "-o",
                        f"UserKnownHostsFile={self.known_hosts}",
                        "-o",
                        "GlobalKnownHostsFile=/dev/null",
                        "-o",
                        "StrictHostKeyChecking=yes",
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "IdentitiesOnly=yes",
                        "-o",
                        "ConnectTimeout=5",
                        "-o",
                        "ConnectionAttempts=1",
                        "-o",
                        "ClearAllForwardings=yes",
                        "-o",
                        "RequestTTY=no",
                        "-o",
                        "LogLevel=ERROR",
                        self.identity + "@" + info["management_address"],
                        self.command,
                    ]
                    proc = await asyncio.create_subprocess_exec(
                        *argv,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                        start_new_session=True,
                    )
                    assert proc.stdin is not None
                    proc.stdin.write(json.dumps(request).encode())
                    await proc.stdin.drain()
                    proc.stdin.close()
                    readers = [
                        asyncio.create_task(read(proc.stdout)),
                        asyncio.create_task(read(proc.stderr)),
                    ]
                    out, err = await asyncio.gather(*readers)
                    code = await proc.wait()
                    if code:
                        if (
                            "Host key verification failed" in err
                            or "REMOTE HOST IDENTIFICATION HAS CHANGED" in err
                        ):
                            result["error_code"] = "host_key_mismatch"
                        elif "Permission denied" in err:
                            result["error_code"] = "ssh_authentication_failed"
                        elif "timed out" in err:
                            result["error_code"] = "connection_timeout"
                        else:
                            result["error_code"] = "node_unavailable"
                    else:
                        try:
                            payload = json.loads(out)
                            allowed = {
                                "status",
                                "data",
                                "raw_evidence",
                                "truncated",
                                "error_code",
                                "duration_ms",
                            }
                            errors = {
                                "invalid_arguments",
                                "denied_operation",
                                "protocol_not_enabled",
                                "network_unreachable",
                                "unknown_interface",
                                "invalid_protocol",
                                "denied_destination",
                                "invalid_count",
                                "mutation_failed",
                                "node_unavailable",
                                "command_failed",
                                "parse_failure",
                                "execution_timeout",
                                "output_limit",
                            }
                            if not isinstance(payload, dict) or set(payload) != allowed:
                                raise ValueError()
                            if (
                                payload["status"] not in {"ok", "error"}
                                or type(payload["truncated"]) is not bool
                                or not isinstance(payload["raw_evidence"], str)
                                or type(payload["duration_ms"]) is not int
                            ):
                                raise ValueError()
                            if payload["status"] == "ok":
                                if payload["error_code"] is not None or not isinstance(
                                    payload["data"], (dict, list)
                                ):
                                    raise ValueError()
                            elif payload["error_code"] not in errors or payload["data"] is not None:
                                raise ValueError()
                            result.update(
                                {
                                    k: payload[k]
                                    for k in ["data", "raw_evidence", "truncated", "error_code"]
                                }
                            )
                            result["status"] = "ok" if payload["status"] == "ok" else "unavailable"
                        except (ValueError, KeyError, TypeError):
                            result["error_code"] = "parse_failure"
        except TimeoutError:
            result["error_code"] = "execution_timeout"
        except OverflowError:
            result.update(error_code="output_limit", truncated=True)
        except OSError:
            result["error_code"] = "node_unavailable"
        finally:
            if proc:
                # Descendants may hold pipes after the SSH parent exits; reap the group too.
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await proc.wait()
            for task in readers:
                if not task.done():
                    task.cancel()
            if readers:
                await asyncio.gather(*readers, return_exceptions=True)
        result["duration_ms"] = round((time.monotonic() - started) * 1000)
        return result
