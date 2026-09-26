import asyncio
import importlib.util
import struct
from unittest.mock import patch

from behave import given, then, when
from minicore_mcp.observer import Store


def api():
    assert importlib.util.find_spec("minicore_mcp.igmp_capture") is not None, (
        "filtered IGMP capture unavailable"
    )
    from minicore_mcp import igmp_capture

    return igmp_capture


def frame(protocol=2, vlan=False):
    def checksum(data):
        data += b"\x00" if len(data) % 2 else b""
        value = sum(struct.unpack("!%dH" % (len(data) // 2), data))
        while value >> 16:
            value = (value & 65535) + (value >> 16)
        return (~value) & 65535

    igmp = bytes.fromhex("16000000ef010101")
    igmp = igmp[:2] + struct.pack("!H", checksum(igmp)) + igmp[4:]
    ip = struct.pack(
        "!BBHHHBBH4s4s",
        0x45,
        0,
        28,
        1,
        0,
        1,
        protocol,
        0,
        bytes([10, 200, 8, 2]),
        bytes([239, 1, 1, 1]),
    )
    ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
    return bytes(12) + (b"\x81\x00" if vlan else b"\x08\x00") + ip + igmp


@when('the IGMP kernel filter sees "{kind}" from "{direction}"')
def filter_packet(c, kind, direction):
    module = api()
    raw = frame({"TCP": 6, "UDP": 17, "OSPF": 89}.get(kind, 2), kind == "VLAN IGMP")
    if kind == "short ethernet":
        raw = bytes(5)
    # Independent classic BPF interpreter for the exact installed instruction array.
    pc = 0
    acc = 0
    c.verdict = 0
    while pc < len(module.FILTER):
        code, jt, jf, k = module.FILTER[pc]
        if code == 0x20 and k == 0xFFFFF004:
            acc = 4 if direction == "outgoing" else 0
        elif code in {0x28, 0x30}:
            size = 2 if code == 0x28 else 1
            if len(raw) < k + size:
                break
            acc = int.from_bytes(raw[k : k + size], "big")
        elif code == 0x15:
            pc += jt if acc == k else jf
        elif code == 0x06:
            c.verdict = k
            break
        else:
            raise AssertionError(f"unsupported BPF instruction {code}")
        pc += 1


@then('its capture verdict is "{verdict}"')
def verdict(c, verdict):
    assert bool(c.verdict) == (verdict == "accept")


@when("packet socket creation is denied by the kernel")
def no_permission(c):
    module = api()
    with patch.object(module.socket, "socket", side_effect=PermissionError()):
        try:
            module.open_tap("veth0")
        except PermissionError:
            c.no_capture = True
        else:
            c.no_capture = False


@then("capture remains unavailable without enabling an unfiltered socket")
def permission_denied(c):
    assert c.no_capture


@given("a mapped IGMP capture source with a volatile store")
def capture_fixture(c):
    module = api()
    c.capture_now = 100.0
    c.capture_store = Store("minicore-local", 1, clock=lambda: c.capture_now)
    c.capture = module.Capture(c.capture_store, clock=lambda: c.capture_now)
    c.binding = {
        "node": "host1",
        "interface": "to-ce1",
        "ifindex": 12,
        "host_name": "veth0",
        "incarnation": "test-first",
    }


@when("a valid sender-side report reaches the callback")
def receive_report(c):
    c.capture.ingest(c.binding, frame(), acquired=100, checksum_partial=False, truncated=False)


@then("only typed IGMP fields and source interface identity are retained")
def typed_report(c):
    records = c.capture_store.snapshot("node:host1:igmp")["records"]
    assert len(records) == 1
    value = records[0]["data"]
    assert (
        value["group"] == "239.1.1.1"
        and value["node_id"] == "host1"
        and value["interface"] == "to-ce1"
    )
    assert not any(k in value for k in ["raw", "payload", "packet"])


@when('capture reports "{condition}"')
def capture_bad(c, condition):
    c.capture.ingest(
        c.binding,
        frame(),
        acquired=30 if condition == "old kernel queue" else 100,
        checksum_partial=condition == "checksum partial",
        truncated=condition == "truncated capture",
    )


@then("no report record is stored and an input error counter increases")
def capture_rejected(c):
    assert c.capture_store.record_count == 0 and sum(c.capture.errors.values()) > 0


@when("an interface incarnation changes or disappears")
def remap(c):
    module = api()
    c.closed_sockets = []

    class Tap:
        def fileno(self):
            return 100 + len(c.closed_sockets)

        def close(self):
            c.closed_sockets.append(True)

        def getsockopt(self, *args):
            return 262144

    async def run():
        with (
            patch.object(module, "open_tap", side_effect=lambda *_: Tap()),
            patch.object(asyncio.get_running_loop(), "add_reader"),
            patch.object(asyncio.get_running_loop(), "remove_reader"),
        ):
            c.capture.reconcile([c.binding])
            c.capture.reconcile([c.binding | {"incarnation": "test-second"}])
            c.capture.reconcile([])

    asyncio.run(run())


@then("old capture descriptors are closed and no old source event is published")
def closed_taps(c):
    assert len(c.closed_sockets) == 2 and not c.capture.taps


@when("an inventoried packet socket is configured")
def socket_order(c):
    module = api()
    c.socket_order = []

    class Tap:
        def setsockopt(self, level, name, value):
            c.socket_order.append(("option", level, name))

        def getsockopt(self, *args):
            return 262144

        def setblocking(self, value):
            pass

        def bind(self, value):
            c.socket_order.append(("bind", value))

        def close(self):
            pass

    with patch.object(module.socket, "socket", return_value=Tap()) as create:
        module.open_tap("veth0")
        c.socket_created = create.call_args.args


@then("its locked IGMP filter precedes link-layer binding and receive buffers are bounded")
def ordered_filter(c):
    import socket

    assert c.socket_created == (socket.AF_PACKET, socket.SOCK_RAW, 0)
    attached = c.socket_order.index(("option", socket.SOL_SOCKET, 26))
    locked = c.socket_order.index(("option", socket.SOL_SOCKET, 44))
    bound = c.socket_order.index(("bind", ("veth0", 3)))
    assert (
        attached < locked < bound
        and ("option", socket.SOL_SOCKET, socket.SO_RCVBUF) in c.socket_order
    )


@when("more than 1024 valid reports arrive within one second")
def burst(c):
    raw = frame()
    for _ in range(1100):
        c.capture.ingest(c.binding, raw, acquired=100, checksum_partial=False, truncated=False)


@then("the remaining reports are dropped and the store record and byte bounds hold")
def burst_bounded(c):
    assert (
        c.capture.errors["rate_limit"] == 76
        and c.capture_store.record_count <= 1024
        and c.capture_store.byte_size <= 8 * 1024 * 1024
    )


def clock_taps(c):
    import socket

    module = api()
    c.wall = 1000.0
    c.fake_taps = []

    class Tap:
        def __init__(self):
            self.closed = False
            self.queue = []
            c.fake_taps.append(self)

        def fileno(self):
            return 120 + c.fake_taps.index(self)

        def getsockopt(self, *args):
            return 262144

        def close(self):
            self.closed = True
            self.queue.clear()

        def recvmsg(self, *args):
            if not self.queue:
                raise BlockingIOError()
            timestamp = self.queue.pop(0)
            sec = int(timestamp)
            anc = [
                (
                    socket.SOL_SOCKET,
                    module.SO_TIMESTAMPNS,
                    struct.pack("@ll", sec, round((timestamp - sec) * 1e9)),
                )
            ]
            return frame(), anc, 0, ("veth0", 3, 0)

    return module, Tap


@when('the capture wall clock steps "{direction}" while a frame is queued')
def clock_step(c, direction):
    module, Tap = clock_taps(c)

    async def run():
        loop = asyncio.get_running_loop()
        with (
            patch.object(module, "open_tap", side_effect=lambda *_: Tap()),
            patch.object(module.time, "time_ns", side_effect=lambda: round(c.wall * 1e9)),
            patch.object(loop, "add_reader"),
            patch.object(loop, "remove_reader"),
        ):
            c.capture.reconcile([c.binding])
            key = (c.binding["node"], c.binding["interface"])
            c.fake_taps[-1].queue.append(c.wall)
            c.capture_now += 1
            c.wall += 1 + (120 if direction == "forward" else -120)
            c.capture._ready(key)
            c.step_snapshot = c.capture_store.snapshot("node:host1:igmp")
            c.step_closed = c.fake_taps[0].closed
            c.step_taps = len(c.capture.taps)
            c.capture_now += 1
            c.wall += 1
            c.capture.reconcile([c.binding])
            c.fake_taps[-1].queue.append(c.wall)
            c.capture._ready(key)
            c.rebound_snapshot = c.capture_store.snapshot("node:host1:igmp")
            c.capture.close()

    asyncio.run(run())


@then("queued frames are discarded and the source becomes unavailable")
def clock_gap(c):
    assert c.step_closed and c.step_taps == 0
    assert (
        not c.step_snapshot["records"] and c.step_snapshot["source_health"] == "source_unavailable"
    )


@then("a rebound source accepts fresh reports without extending old record age")
def clock_recovered(c):
    rows = c.rebound_snapshot["records"]
    assert len(rows) == 1 and c.rebound_snapshot["source_health"] == "ok"
    assert rows[0]["acquired_monotonic"] == c.capture_now


@when("the callback receives a frame queued for seventy seconds with stable clocks")
def kernel_old(c):
    module, Tap = clock_taps(c)

    async def run():
        loop = asyncio.get_running_loop()
        with (
            patch.object(module, "open_tap", side_effect=lambda *_: Tap()),
            patch.object(module.time, "time_ns", side_effect=lambda: round(c.wall * 1e9)),
            patch.object(loop, "add_reader"),
            patch.object(loop, "remove_reader"),
        ):
            c.capture.reconcile([c.binding])
            c.fake_taps[-1].queue.append(c.wall)
            c.capture_now += 70
            c.wall += 70
            c.capture._ready((c.binding["node"], c.binding["interface"]))
            c.capture.close()

    asyncio.run(run())
