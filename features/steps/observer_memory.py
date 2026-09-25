import asyncio
import importlib.util
import json
from unittest.mock import patch

from behave import given, then, when


def api():
    assert importlib.util.find_spec("minicore_mcp.observer") is not None, (
        "volatile observer not implemented"
    )
    from minicore_mcp.observer import Coordinator, Store

    return Store, Coordinator


def sample(value=1):
    return {
        "interfaces": [
            {
                "interface": "to-p2",
                "tx_packets": value,
                "rx_packets": value,
                "tx_bytes": value * 64,
                "rx_bytes": value * 64,
                "state": "UP",
            }
        ]
    }


@given("an observer with a controllable monotonic clock")
def memory(c):
    Store, _ = api()
    c.now = 100.0
    c.store = Store("minicore-local", 1, clock=lambda: c.now)


@given("a small bounded observer store")
def small_store(c):
    Store, _ = api()
    c.now = 100.0
    c.store = Store("minicore-local", 1, clock=lambda: c.now, max_bytes=1300, max_records=3)


@when("routing and counter records reach sixty seconds old")
def expiry(c):
    c.store.put("node:p1:interfaces", sample(), acquired=100.0, incarnation="first")
    c.now = 101
    c.store.put("node:p1:interfaces", sample(2), acquired=101.0, incarnation="first")
    c.now = 161


@then("neither current records nor previous comparison baselines remain")
def expired(c):
    assert c.store.snapshot("node:p1:interfaces")["records"] == []
    assert c.store.byte_size == 0 and c.store.record_count == 0


@when("a host record arrives sixty seconds after its acquisition")
def old_ipc(c):
    c.accepted = c.store.put("node:p1:interfaces", sample(), acquired=40, incarnation="first")


@then("it is discarded rather than becoming a fresh sample")
def ipc_rejected(c):
    assert c.accepted is False and c.store.record_count == 0


@when("more complete records arrive than its capacity")
def overflow(c):
    for i in range(10):
        c.now += 1
        c.store.put("node:p1:interfaces", sample(i), acquired=c.now, incarnation="first")


@then("memory and entry limits hold and eviction is reported")
def bounded(c):
    value = c.store.snapshot("node:p1:interfaces")
    assert c.store.record_count <= 3 and c.store.byte_size <= 1300
    assert value["missed_updates"] > 0 and value["records"][-1]["data"] == sample(9)


@when("its lab generation or source incarnation changes")
def scope_change(c):
    c.store.put("node:p1:interfaces", sample(), acquired=100, incarnation="old")
    c.store.put("node:p1:interfaces", sample(3), acquired=100, incarnation="new")
    assert [r["data"] for r in c.store.snapshot("node:p1:interfaces")["records"]] == [sample(3)]
    c.before_epoch = c.store.epoch
    c.store.reset(2)


@then("no prior identity record or comparison baseline is returned")
def scope_empty(c):
    value = c.store.snapshot("node:p1:interfaces")
    assert value["generation"] == 2 and value["records"] == [] and c.store.epoch != c.before_epoch


@when("a scoped response cannot fit all eligible records")
def response_cap(c):
    for i in range(10):
        c.now += 1
        c.store.put("node:p1:interfaces", sample(i), acquired=c.now, incarnation="first")
    c.response = c.store.snapshot("node:p1:interfaces", limit_bytes=1200)


@then("whole records are truncated with omitted counts within the response limit")
def response_bounded(c):
    assert len(json.dumps(c.response, separators=(",", ":")).encode()) <= 1200
    assert c.response["truncated"] and c.response["omitted"] > 0
    assert c.response["records"][-1]["data"] == sample(9)


@then("a second read does not change the acquisition times")
def read_age(c):
    stamps = [r["acquired_monotonic"] for r in c.store.snapshot("node:p1:interfaces")["records"]]
    c.now += 1
    assert stamps == [
        r["acquired_monotonic"] for r in c.store.snapshot("node:p1:interfaces")["records"]
    ]


@when("arbitrary payload bytes or raw output are submitted to the store")
def reject_raw(c):
    with patch("builtins.open", side_effect=AssertionError("filesystem write")):
        c.invalid = 0
        for data in [
            b"raw bytes",
            {"raw_evidence": "secret packet"},
            {"payload": "data"},
            {"interfaces": [{"interface": "to-p2", "payload": "hidden"}]},
        ]:
            try:
                c.store.put("node:p1:interfaces", data, acquired=c.now, incarnation="first")
            except ValueError:
                c.invalid += 1


@then("they are rejected and no observer data reaches the filesystem")
def no_raw(c):
    assert c.invalid == 4 and c.store.record_count == 0


@given("a coordinator with two bounded asynchronous sources")
def coordinator(c):
    api()


@when("concurrent clients read while collection is pending")
def shared_collection(c):
    async def run():
        Store, Coordinator = api()
        store = Store("minicore-local", 1)
        coordinator = Coordinator(store, interval=0.02, timeout=0.3, concurrency=2)
        calls = {"a": 0, "b": 0}
        release = asyncio.Event()

        async def source(key):
            calls[key] += 1
            await release.wait()
            return sample(), key

        coordinator.add("node:p1:interfaces", lambda: source("a"))
        coordinator.add("node:p2:interfaces", lambda: source("b"))
        await coordinator.start()
        await asyncio.sleep(0.04)

        async def client():
            store.snapshot("node:p1:interfaces")
            await asyncio.sleep(10)

        task = asyncio.create_task(client())
        await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        c.calls = dict(calls)
        release.set()
        await asyncio.sleep(0.005)
        c.fresh = bool(store.snapshot("node:p1:interfaces")["records"])
        await coordinator.close()
        c.closed = not coordinator.tasks and store.record_count == 0

    asyncio.run(run())


@then("each source executes at most once and cancelling a reader does not stop collection")
def collection_shared(c):
    assert c.calls == {"a": 1, "b": 1} and c.fresh and c.closed


@when("one source stalls beyond its deadline")
def stalled(c):
    async def run():
        Store, Coordinator = api()
        store = Store("minicore-local", 1)
        coordinator = Coordinator(store, interval=0.1, timeout=0.04, concurrency=2)

        async def slow():
            await asyncio.sleep(10)
            return sample(), "slow"

        async def fast():
            return sample(), "fast"

        coordinator.add("node:p1:interfaces", slow)
        coordinator.add("node:p2:interfaces", fast)
        await coordinator.start()
        timer = asyncio.get_running_loop().time()
        await asyncio.sleep(0.06)
        c.elapsed = asyncio.get_running_loop().time() - timer
        c.fast = store.snapshot("node:p2:interfaces")
        c.slow = store.snapshot("node:p1:interfaces")
        await coordinator.close()
        c.closed = not coordinator.tasks and store.record_count == 0

    asyncio.run(run())


@then("the healthy source is published and the loop remains responsive")
def healthy(c):
    assert c.elapsed < 0.2 and c.fast["records"] and c.slow["source_health"] == "collection_timeout"


@then("coordinator shutdown clears observations and releases all tasks")
def closed(c):
    assert c.closed


@when("valid v2 and v3 reports are parsed and put into the observer")
def parsed_ingest(c):
    import struct

    from minicore_mcp.igmp import parse_igmp_ethernet_frame

    def checksum(data):
        data += b"\x00" if len(data) % 2 else b""
        value = sum(struct.unpack("!%dH" % (len(data) // 2), data))
        while value >> 16:
            value = (value & 65535) + (value >> 16)
        return (~value) & 65535

    c.ingested = []
    for igmp in [
        bytes.fromhex("16000000ef010101"),
        bytes.fromhex("2200000000000001") + bytes.fromhex("02000000ef010101"),
    ]:
        igmp = igmp[:2] + struct.pack("!H", checksum(igmp)) + igmp[4:]
        ip = struct.pack(
            "!BBHHHBBH4s4s",
            0x45,
            0,
            20 + len(igmp),
            1,
            0,
            1,
            2,
            0,
            bytes([10, 200, 8, 2]),
            bytes([224, 0, 0, 22]),
        )
        ip = ip[:10] + struct.pack("!H", checksum(ip)) + ip[12:]
        parsed = parse_igmp_ethernet_frame(
            bytes(12) + b"\x08\x00" + ip + igmp, checksum_policy="verified"
        )
        c.ingested.append(
            c.store.put("link:host1-ce1:igmp", parsed, acquired=c.now, incarnation="host1-to-ce1")
        )


@then("both typed events are present without packet bytes or application fields")
def typed_ingest(c):
    value = c.store.snapshot("link:host1-ce1:igmp")
    assert c.ingested == [True, True] and len(value["records"]) == 2
    assert all(
        set(row["data"])
        == {"version", "message_type", "group", "reporter", "querier", "sources", "records"}
        for row in value["records"]
    )


@when("the store generation changes during a slow successful collection")
def generation_inflight(c):
    async def run():
        Store, Coordinator = api()
        store = Store("minicore-local", 1)
        coordinator = Coordinator(store, interval=10, timeout=1)
        began = asyncio.Event()
        release = asyncio.Event()

        async def source():
            began.set()
            await release.wait()
            return sample(), "old"

        coordinator.add("node:p1:interfaces", source)
        await coordinator.start()
        await began.wait()
        store.reset(2)
        release.set()
        await asyncio.sleep(0.02)
        c.after_generation = store.snapshot("node:p1:interfaces")
        await coordinator.close()

    asyncio.run(run())


@then("the old collection result is discarded before publication")
def discarded_inflight(c):
    assert c.after_generation["generation"] == 2 and c.after_generation["records"] == []
