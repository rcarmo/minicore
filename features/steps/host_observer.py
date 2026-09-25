import asyncio
import copy
import json
import socket
import struct
from pathlib import Path

from behave import given, then, when

ROOT = Path(__file__).resolve().parents[2]
ZERO = {
    k: 0
    for k in [
        "rx_packets",
        "tx_packets",
        "rx_bytes",
        "tx_bytes",
        "rx_errors",
        "tx_errors",
        "rx_dropped",
        "tx_dropped",
    ]
}


class Recorder:
    def __init__(self, outputs):
        self.outputs = {tuple(k): v for k, v in outputs.items()}
        self.calls = []

    async def __call__(self, argv, *, timeout=5.0, limit=65536):
        key = tuple(argv)
        self.calls.append(list(argv))
        assert timeout == 5.0 and limit == 65536
        if key not in self.outputs:
            raise AssertionError(f"unexpected command: {argv}")
        if isinstance(self.outputs[key], Exception):
            raise self.outputs[key]
        return self.outputs[key]


def nlattr(kind, payload):
    size = 4 + len(payload)
    return struct.pack("HH", size, kind) + payload + (b"\x00" * (((size + 3) & ~3) - size))


def ifinfomsg(index):
    return struct.pack("BBHiII", socket.AF_UNSPEC, 0, 0, index, 0, 0)


def stats64(**values):
    keys = list(ZERO)
    return struct.pack("Q" * len(keys), *(values[k] for k in keys))


def link_message(index, *, name, master=None, peer=None, stats=None, done=False):
    attrs = [nlattr(3, name.encode() + b"\x00")]
    if master is not None:
        attrs.append(nlattr(10, struct.pack("I", master)))
    if peer is not None:
        attrs.append(nlattr(5, struct.pack("I", peer)))
    if stats is not None:
        attrs.append(nlattr(23, stats64(**stats)))
    payload = ifinfomsg(index) + b"".join(attrs)
    return struct.pack("IHHII", 16 + len(payload), 3 if done else 16, 2, 1, 0) + payload


def host_dump(entries):
    return b"".join(entries + [struct.pack("IHHII", 16, 3, 0, 1, 0)])


def inventory():
    value = json.loads((ROOT / "inventory/topology.json").read_text())
    keep_nodes = {"ce1", "pe1", "host1"}
    keep_links = {"ce1-pe1", "host1-ce1"}
    value["nodes"] = [n for n in value["nodes"] if n["id"] in keep_nodes]
    value["links"] = [link for link in value["links"] if link["id"] in keep_links]
    return value


@given("the current inventory and fixed Docker inspect and exec responses")
def fixed_topology(context):
    context.inventory = inventory()
    context.outputs = {
        ("docker", "inspect", "minicore-ce1-1", "minicore-host1-1", "minicore-pe1-1"): json.dumps(
            [
                {
                    "Id": "cid-ce1",
                    "Name": "/minicore-ce1-1",
                    "State": {"Running": True},
                    "NetworkSettings": {
                        "Networks": {
                            "management": {"NetworkID": "mgmtid"},
                            "link_ce1_pe1": {"NetworkID": "a1b2c3d4e5f6"},
                            "link_host1_ce1": {"NetworkID": "0f1e2d3c4b5a"},
                        }
                    },
                },
                {
                    "Id": "cid-host1",
                    "Name": "/minicore-host1-1",
                    "State": {"Running": True},
                    "NetworkSettings": {
                        "Networks": {
                            "management": {"NetworkID": "mgmtid"},
                            "link_host1_ce1": {"NetworkID": "0f1e2d3c4b5a"},
                        }
                    },
                },
                {
                    "Id": "cid-pe1",
                    "Name": "/minicore-pe1-1",
                    "State": {"Running": True},
                    "NetworkSettings": {
                        "Networks": {
                            "management": {"NetworkID": "mgmtid"},
                            "link_ce1_pe1": {"NetworkID": "a1b2c3d4e5f6"},
                        }
                    },
                },
            ]
        ),
        ("docker", "inspect", "link_ce1_pe1", "link_host1_ce1"): json.dumps(
            [
                {"Name": "link_ce1_pe1", "Options": {}, "Id": "a1b2c3d4e5f6"},
                {"Name": "link_host1_ce1", "Options": {}, "Id": "0f1e2d3c4b5a"},
            ]
        ),
        ("docker", "exec", "minicore-ce1-1", "ip", "-j", "link", "show"): json.dumps(
            [
                {"ifindex": 1, "ifname": "lo"},
                {"ifindex": 2, "ifname": "eth0", "link_index": 999, "operstate": "UP"},
                {"ifindex": 3, "ifname": "to-pe1", "link_index": 1101, "operstate": "UP"},
                {"ifindex": 4, "ifname": "to-host1", "link_index": 1102, "operstate": "UP"},
            ]
        ),
        ("docker", "exec", "minicore-host1-1", "ip", "-j", "link", "show"): json.dumps(
            [
                {"ifindex": 1, "ifname": "lo"},
                {"ifindex": 2, "ifname": "eth0", "link_index": 998, "operstate": "UP"},
                {"ifindex": 3, "ifname": "to-ce1", "link_index": 2101, "operstate": "UP"},
            ]
        ),
        ("docker", "exec", "minicore-pe1-1", "ip", "-j", "link", "show"): json.dumps(
            [
                {"ifindex": 1, "ifname": "lo"},
                {"ifindex": 2, "ifname": "eth0", "link_index": 997, "operstate": "UP"},
                {"ifindex": 3, "ifname": "to-ce1", "link_index": 3101, "operstate": "UP"},
            ]
        ),
    }
    context.outputs[
        (
            "docker",
            "exec",
            "minicore-host1-1",
            "cat",
            "/sys/class/net/to-ce1/ifindex",
            "/sys/class/net/to-ce1/iflink",
            "/sys/class/net/to-ce1/operstate",
        )
    ] = "3\n2101\nup\n"
    context.netlink = host_dump(
        [
            link_message(901, name="br-a1b2c3d4e5f6", stats=ZERO),
            link_message(902, name="br-0f1e2d3c4b5a", stats=ZERO),
            link_message(
                1101,
                name="veth-ce1-pe1",
                master=901,
                peer=3,
                stats={
                    "rx_packets": 10,
                    "tx_packets": 7,
                    "rx_bytes": 1000,
                    "tx_bytes": 700,
                    "rx_errors": 1,
                    "tx_errors": 2,
                    "rx_dropped": 3,
                    "tx_dropped": 4,
                },
            ),
            link_message(
                1102,
                name="veth-ce1-h1",
                master=902,
                peer=4,
                stats={
                    "rx_packets": 20,
                    "tx_packets": 21,
                    "rx_bytes": 2000,
                    "tx_bytes": 2100,
                    "rx_errors": 0,
                    "tx_errors": 1,
                    "rx_dropped": 1,
                    "tx_dropped": 2,
                },
            ),
            link_message(
                2101,
                name="veth-h1-ce1",
                master=902,
                peer=3,
                stats={
                    "rx_packets": 30,
                    "tx_packets": 31,
                    "rx_bytes": 3000,
                    "tx_bytes": 3100,
                    "rx_errors": 4,
                    "tx_errors": 5,
                    "rx_dropped": 6,
                    "tx_dropped": 7,
                },
            ),
            link_message(
                3101, name="veth-pe1-ce1", master=901, peer=3, stats=ZERO | {"rx_packets": 10}
            ),
            link_message(777, name="docker0", stats=ZERO),
        ]
    )

    containers_key = ("docker", "inspect", "minicore-ce1-1", "minicore-host1-1", "minicore-pe1-1")
    containers = json.loads(context.outputs[containers_key])
    for container in containers:
        name = container["Name"].removeprefix("/minicore-").removesuffix("-1")
        container["Config"] = {
            "Labels": {
                "io.minicore.node": name,
                "io.minicore.lab": context.inventory["lab_id"],
                "com.docker.compose.service": name,
                "com.docker.compose.project": "minicore",
            }
        }
        container["NetworkSettings"]["Networks"] = {
            "minicore_" + network: entry
            for network, entry in container["NetworkSettings"]["Networks"].items()
        }
        context.outputs[("docker", "inspect", container["Name"].removeprefix("/"))] = json.dumps(
            [container]
        )
    context.outputs[containers_key] = json.dumps(containers)
    networks = json.loads(
        context.outputs.pop(("docker", "inspect", "link_ce1_pe1", "link_host1_ce1"))
    )
    for network in networks:
        raw = network["Name"]
        network["Name"] = "minicore_" + raw
        network["Driver"] = "bridge"
        network["Labels"] = {
            "com.docker.compose.project": "minicore",
            "com.docker.compose.network": raw,
        }
    context.outputs[
        ("docker", "network", "inspect", "minicore_link_ce1_pe1", "minicore_link_host1_ce1")
    ] = json.dumps(networks)


@given("one node has no matching host peer while another remains healthy")
def one_failure(context):
    fixed_topology(context)
    broken = json.loads(
        context.outputs[("docker", "exec", "minicore-ce1-1", "ip", "-j", "link", "show")]
    )
    for row in broken:
        if row.get("ifname") == "to-host1":
            row["link_index"] = 9999
    context.outputs[("docker", "exec", "minicore-ce1-1", "ip", "-j", "link", "show")] = json.dumps(
        broken
    )


@when("the isolated Linux host observer collects interfaces")
def collect(context):
    from minicore_mcp.observer_host import collect_interfaces, dump_links

    async def run():
        recorder = Recorder(context.outputs)
        context.recorder = recorder
        context.result = await collect_interfaces(
            copy.deepcopy(context.inventory),
            run_command=recorder,
            netlink_reader=lambda: dump_links(loader=lambda: [context.netlink]),
        )

    asyncio.run(run())


@then("each inventoried data endpoint is mapped through container and host peer indexes")
def mapped(context):
    ce1 = context.result["ce1"]
    host1 = context.result["host1"]
    pe1 = context.result["pe1"]
    assert ce1["_internal"]["container_id"] == "cid-ce1"
    assert {m["interface"]: m["host_ifindex"] for m in ce1["_internal"]["mappings"]} == {
        "to-pe1": 1101,
        "to-host1": 1102,
    }
    assert host1["_internal"]["mappings"][0]["host_ifindex"] == 2101
    assert pe1["_internal"]["mappings"][0]["host_ifindex"] == 3101


@then("host RX counters are exposed as container transmit and host TX as container receive")
def translated(context):
    rows = {row["interface"]: row for row in context.result["ce1"]["data"]["interfaces"]}
    assert rows["to-pe1"] == {
        "interface": "to-pe1",
        "state": "UP",
        "tx_packets": 10,
        "rx_packets": 7,
        "tx_bytes": 1000,
        "rx_bytes": 700,
        "tx_errors": 1,
        "rx_errors": 2,
        "tx_drops": 3,
        "rx_drops": 4,
    }


@then("the observer uses only fixed inventory Docker commands and a host rtnetlink dump")
def fixed_calls(context):
    assert sorted(context.recorder.calls) == sorted(
        [
            ["docker", "inspect", "minicore-ce1-1"],
            ["docker", "inspect", "minicore-host1-1"],
            ["docker", "inspect", "minicore-pe1-1"],
            ["docker", "network", "inspect", "minicore_link_ce1_pe1", "minicore_link_host1_ce1"],
            ["docker", "exec", "minicore-ce1-1", "ip", "-j", "link", "show"],
            [
                "docker",
                "exec",
                "minicore-host1-1",
                "cat",
                "/sys/class/net/to-ce1/ifindex",
                "/sys/class/net/to-ce1/iflink",
                "/sys/class/net/to-ce1/operstate",
            ],
            ["docker", "exec", "minicore-pe1-1", "ip", "-j", "link", "show"],
        ]
    )


@then("the healthy node still returns translated interface counters")
def healthy(context):
    assert context.result["host1"]["data"]["interfaces"][0]["tx_packets"] == 30


@then("the failed node reports a typed discovery error")
def typed_error(context):
    assert context.result["ce1"]["error_code"] == "endpoint_unmapped"
    assert context.result["pe1"]["data"]["interfaces"][0]["tx_packets"] == 10


@then("management and unrelated host interfaces are excluded")
def excluded(context):
    host1 = context.result["host1"]
    assert [row["interface"] for row in host1["data"]["interfaces"]] == ["to-ce1"]
    assert all("eth0" not in json.dumps(row) for row in host1["data"]["interfaces"])


@given("Docker uses Compose-prefixed network names with inventory labels")
def real_names(context):
    fixed_topology(context)


@then("healthy data endpoints map using the actual network identities")
def real_mappings(context):
    assert all("data" in value for value in context.result.values()), context.result


@given('a netlink dump with "{fault}"')
def bad_dump(context, fault):
    from minicore_mcp import observer_host as module

    frame = link_message(
        4, name="veth-test", master=3, peer=2, stats={key: 1 for key in module._STATS}
    )
    done = struct.pack("IHHII", 16, 3, 0, 1, 0)
    if fault == "error message":
        context.bad_bytes = struct.pack("IHHIIi", 20, 2, 0, 1, 0, -1)
    if fault == "missing done":
        context.bad_bytes = frame
    if fault == "interrupted dump":
        context.bad_bytes = frame + struct.pack("IHHII", 16, 3, 0x10, 1, 0)
    if fault == "short stats":
        body = ifinfomsg(4) + nlattr(3, b"veth-test\0") + nlattr(23, bytes(8))
        context.bad_bytes = struct.pack("IHHII", 16 + len(body), 16, 0, 1, 0) + body + done
    if fault == "trailing bytes":
        context.bad_bytes = frame + done + b"bad"


@when("the host decodes the bounded dump")
def decode_bad(context):
    from minicore_mcp import observer_host as module

    try:
        module._parse_links(context.bad_bytes)
    except ValueError:
        context.dump_denied = True
    else:
        context.dump_denied = False


@then("it rejects the dump as incomplete or malformed")
def dump_rejected(context):
    assert context.dump_denied


@given("an inventoried peer lacks complete statistics")
def missing_stats(context):
    context.netlink = host_dump(
        [
            link_message(901, name="br-a1b2c3d4e5f6", stats=ZERO),
            link_message(902, name="br-0f1e2d3c4b5a", stats=ZERO),
            link_message(1101, name="veth-ce1-pe1", master=901, peer=3),
            link_message(1102, name="veth-ce1-h1", master=902, peer=4, stats=ZERO),
        ]
    )


@then("that node reports unavailable counters instead of zero rates")
def unavailable_stats(context):
    assert context.result["ce1"].get("error_code") == "counters_unavailable", context.result


@given("one container has the wrong Minicore node label")
def wrong_label(context):
    key = ("docker", "inspect", "minicore-ce1-1", "minicore-host1-1", "minicore-pe1-1")
    containers = json.loads(context.outputs[key])
    containers[0]["Config"]["Labels"]["io.minicore.node"] = "p2"
    context.outputs[key] = json.dumps(containers)
    context.outputs[("docker", "inspect", "minicore-ce1-1")] = json.dumps([containers[0]])


@then("that node identity is rejected while other nodes remain visible")
def bad_identity(context):
    assert context.result["ce1"].get("error_code") == "identity_mismatch" and context.result[
        "host1"
    ].get("data"), context.result


@given("one inventoried container is missing during discovery")
def missing_container(context):
    context.outputs[("docker", "inspect", "minicore-ce1-1")] = RuntimeError("command_failed")
    context.outputs[
        ("docker", "inspect", "minicore-ce1-1", "minicore-host1-1", "minicore-pe1-1")
    ] = RuntimeError("command_failed")


@then("the missing node is unavailable while healthy nodes still publish counters")
def isolated_missing(context):
    assert (
        context.result["ce1"].get("error_code")
        and context.result["host1"].get("data")
        and context.result["pe1"].get("data")
    ), context.result


@given("the endpoint has only fixed interface metadata files")
def busybox_endpoint(context):
    context.outputs[("docker", "exec", "minicore-host1-1", "ip", "-j", "link", "show")] = (
        RuntimeError("command_failed")
    )
    context.outputs[
        (
            "docker",
            "exec",
            "minicore-host1-1",
            "cat",
            "/sys/class/net/to-ce1/ifindex",
            "/sys/class/net/to-ce1/iflink",
            "/sys/class/net/to-ce1/operstate",
        )
    ] = "3\n2101\nup\n"


@then("the endpoint maps through fixed read-only metadata without a shell")
def endpoint_metadata(context):
    assert context.result["host1"].get("data"), context.result["host1"]
    assert [
        "docker",
        "exec",
        "minicore-host1-1",
        "cat",
        "/sys/class/net/to-ce1/ifindex",
        "/sys/class/net/to-ce1/iflink",
        "/sys/class/net/to-ce1/operstate",
    ] in context.recorder.calls
