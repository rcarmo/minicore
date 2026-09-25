"""Linux IGMP-only packet sockets. No packet persistence or broad packet decoder."""

import asyncio
import ctypes
import socket
import struct
import time

from .igmp import IGMPParseError, parse_igmp_ethernet_frame

SOL_PACKET = 263
PACKET_AUXDATA = 8
PACKET_STATISTICS = 6
SO_TIMESTAMPNS = 35
MAX_FRAME = 2048
# classic BPF: reject host outgoing copies, non-IPv4, and all protocols but IGMP.
FILTER = (
    (0x20, 0, 0, 0xFFFFF004),
    (0x15, 5, 0, 4),
    (0x28, 0, 0, 12),
    (0x15, 0, 3, 0x0800),
    (0x30, 0, 0, 23),
    (0x15, 0, 1, 2),
    (0x06, 0, 0, MAX_FRAME),
    (0x06, 0, 0, 0),
)


class Instruction(ctypes.Structure):
    _fields_ = [
        ("code", ctypes.c_ushort),
        ("jt", ctypes.c_ubyte),
        ("jf", ctypes.c_ubyte),
        ("k", ctypes.c_uint),
    ]


class Program(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("instructions", ctypes.POINTER(Instruction))]


def open_tap(interface):
    # Protocol zero receives nothing until bind; install and lock the filter first.
    sock = socket.socket(socket.AF_PACKET, socket.SOCK_RAW, 0)
    try:
        program = (Instruction * len(FILTER))(*(Instruction(*row) for row in FILTER))
        header = Program(len(FILTER), program)
        sock.setsockopt(socket.SOL_SOCKET, 26, bytes(header))  # SO_ATTACH_FILTER
        sock.setsockopt(socket.SOL_SOCKET, 44, 1)  # SO_LOCK_FILTER
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 128 * 1024)
        if sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) > 512 * 1024:
            raise ValueError("capture_buffer_limit")
        sock.setsockopt(socket.SOL_SOCKET, SO_TIMESTAMPNS, 1)
        sock.setsockopt(SOL_PACKET, PACKET_AUXDATA, 1)
        sock.setblocking(False)
        # Bridge ingress reaches ETH_P_ALL sockets before L3 dispatch. The locked
        # filter above still admits only IPv4/IGMP and rejects host-outgoing copies.
        sock.bind((interface, 3))
        return sock
    except BaseException:
        sock.close()
        raise


class Capture:
    def __init__(self, store, *, clock=time.monotonic):
        self.store = store
        self.clock = clock
        self.taps = {}
        self.errors = {
            key: 0
            for key in [
                "parse",
                "truncated",
                "checksum_partial",
                "expired",
                "socket_unavailable",
                "kernel_drops",
                "rate_limit",
            ]
        }
        self._budget_second = -1
        self._budget_count = 0

    def _error(self, code):
        self.errors[code] = min(2**53 - 1, self.errors[code] + 1)
        self.store._missed()

    def ingest(self, binding, raw, *, acquired, checksum_partial, truncated):
        if truncated:
            self._error("truncated")
            return
        if checksum_partial:
            self._error("checksum_partial")
            return
        if not 0 <= self.clock() - acquired < 60:
            self._error("expired")
            return
        second = int(self.clock())
        if self._budget_second != second:
            self._budget_second = second
            self._budget_count = 0
        self._budget_count += 1
        if self._budget_count > 1024:
            self._error("rate_limit")
            return
        try:
            value = parse_igmp_ethernet_frame(raw, checksum_policy="verified")
            value.update(node_id=binding["node"], interface=binding["interface"])
            self.store.put(
                "node:" + binding["node"] + ":igmp",
                value,
                acquired=acquired,
                incarnation=binding["incarnation"],
            )
        except (IGMPParseError, ValueError):
            self._error("parse")

    def _ready(self, key):
        if key not in self.taps:
            return
        sock, binding = self.taps[key]
        # Bounded work per callback; the loop can serve IPC/timers under a storm.
        for _ in range(16):
            try:
                raw, anc, flags, address = sock.recvmsg(MAX_FRAME, 256, socket.MSG_DONTWAIT)
            except BlockingIOError:
                return
            except OSError:
                self._error("socket_unavailable")
                self._close(key)
                return
            if len(address) < 3 or address[2] == 4:
                continue
            wall_ns = None
            partial = False
            for level, kind, data in anc:
                if level == socket.SOL_SOCKET and kind == SO_TIMESTAMPNS and len(data) >= 16:
                    sec, nsec = struct.unpack_from("@ll", data)
                    wall_ns = sec * 1000000000 + nsec
                if level == SOL_PACKET and kind == PACKET_AUXDATA and len(data) >= 4:
                    partial = bool(struct.unpack_from("I", data)[0] & 8)
            age = (time.time_ns() - wall_ns) / 1e9 if wall_ns is not None else None
            if age is None or age < -0.01 or age >= 60:
                self._error("expired")
                continue
            self.ingest(
                binding,
                raw,
                acquired=self.clock() - max(0, age),
                checksum_partial=partial,
                truncated=bool(flags & (socket.MSG_TRUNC | socket.MSG_CTRUNC)),
            )
            # raw and ancillary data leave scope; neither is enqueued or logged.

    def _close(self, key):
        sock, binding = self.taps.pop(key)
        asyncio.get_running_loop().remove_reader(sock.fileno())
        sock.close()

    def reconcile(self, bindings):
        if len(bindings) > 18:
            raise ValueError("capture_interface_limit")
        desired = {(b["node"], b["interface"]): b for b in bindings}
        for key, (_, old) in list(self.taps.items()):
            if key not in desired or desired[key] != old:
                self._close(key)
        total = sum(
            sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF) for sock, _ in self.taps.values()
        )
        for key, binding in desired.items():
            if key in self.taps:
                continue
            try:
                sock = open_tap(binding["host_name"])
                size = sock.getsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF)
                if total + size > 8 * 1024 * 1024:
                    sock.close()
                    raise ValueError("capture_buffer_limit")
                total += size
                self.taps[key] = (sock, binding)
                asyncio.get_running_loop().add_reader(sock.fileno(), self._ready, key)
            except (OSError, ValueError):
                self._error("socket_unavailable")
        nodes = {b["node"]: b["incarnation"] for b in bindings}
        for scope in list(self.store._scopes):
            if scope.endswith(":igmp") and scope.split(":")[1] not in nodes:
                self.store.health(scope, "source_unavailable", "unbound")
        # Keep quiet healthy sources visible as No recent reports; no invented rows.
        for node, incarnation in nodes.items():
            good = all(key in self.taps for key in desired if key[0] == node)
            self.store.health(
                "node:" + node + ":igmp", "ok" if good else "source_unavailable", incarnation
            )

    def poll_stats(self):
        for sock, _ in self.taps.values():
            try:
                _, dropped = struct.unpack("II", sock.getsockopt(SOL_PACKET, PACKET_STATISTICS, 8))
                if dropped:
                    self.errors["kernel_drops"] = min(
                        2**53 - 1, self.errors["kernel_drops"] + dropped
                    )
                    self.store._missed()
            except OSError:
                self._error("socket_unavailable")

    def close(self):
        for key in list(self.taps):
            self._close(key)
