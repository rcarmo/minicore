import asyncio
import json
from pathlib import Path

from behave import given, then, when

ROOT = Path(__file__).resolve().parents[2]


@when("the asyncio host observer reads the running eight-node lab")
def host_live(c):
    from minicore_mcp.observer_host import collect_interfaces

    inventory = json.loads((ROOT / "inventory/topology.json").read_text())
    c.observer_live = asyncio.run(collect_interfaces(inventory))


@then("all eighteen data endpoints have fresh mapped counters and no management interface")
def all_mapped(c):
    assert len(c.observer_live) == 8 and all("data" in row for row in c.observer_live.values()), (
        c.observer_live
    )
    rows = [
        interface for row in c.observer_live.values() for interface in row["data"]["interfaces"]
    ]
    assert len(rows) == 18 and all(
        row["interface"].startswith("to-") and row["tx_packets"] >= 0 for row in rows
    ), rows


@then("public counter records contain no container identities or raw command output")
def no_internal(c):
    from minicore_mcp.observer import Store

    store = Store("minicore-local", 1)
    for node, row in c.observer_live.items():
        store.put(
            f"node:{node}:interfaces",
            row["data"],
            acquired=row["acquired"],
            incarnation=row["incarnation"],
        )
    for node in c.observer_live:
        response = store.snapshot(f"node:{node}:interfaces")
        assert response["records"]
        body = json.dumps(response["records"][0]["data"])
        assert "_internal" not in body and "container_id" not in body and "raw_evidence" not in body


@when("two host interface samples bracket a bounded endpoint probe")
def counter_probe(c):
    from minicore_mcp.observer_host import collect_interfaces, run_command

    inventory = json.loads((ROOT / "inventory/topology.json").read_text())

    async def run():
        before = await collect_interfaces(inventory)
        await run_command(
            ["docker", "exec", "minicore-host1-1", "ping", "-c", "2", "-W", "1", "10.200.8.3"]
        )
        after = await collect_interfaces(inventory)
        return before, after

    c.counter_before, c.counter_after = asyncio.run(run())


@then("endpoint transmit and receive packet deltas increase without negative counters")
def counter_direction(c):
    before = c.counter_before["host1"]["data"]["interfaces"][0]
    after = c.counter_after["host1"]["data"]["interfaces"][0]
    assert (
        after["tx_packets"] - before["tx_packets"] >= 2
        and after["rx_packets"] - before["rx_packets"] >= 2
    ), (before, after)
    assert c.counter_before["host1"]["incarnation"] == c.counter_after["host1"]["incarnation"]


@when("the deployed observer sources have collected router and endpoint data")
def live_service_ready(c):
    import time

    import httpx

    deadline = time.monotonic() + 65
    while time.monotonic() < deadline:
        r = httpx.get(
            "http://127.0.0.1:19000/api/v1/observer?scope=node&node_id=p1&kind=routing", timeout=10
        )
        c.live_observation = r.json()
        if (
            r.status_code == 200
            and c.live_observation.get("records")
            and c.live_observation.get("source_health") == "ok"
        ):
            return
        time.sleep(1)
    raise AssertionError(c.live_observation)


@then("real HTTP node and link scopes return bounded current counters and routing sources")
def live_scopes(c):
    import httpx

    for query in [
        "scope=node&node_id=host1&kind=interfaces",
        "scope=node&node_id=p1&kind=routing",
        "scope=link&link_id=p1-p2&kind=interfaces",
    ]:
        r = httpx.get("http://127.0.0.1:19000/api/v1/observer?" + query, timeout=10)
        value = r.json()
        assert r.status_code == 200 and value["source_health"] == "ok" and value["records"], value
        assert len(r.content) <= 65536 and all(
            0 <= row["remaining_ms"] <= 60000 for row in value["records"]
        )
        assert r.headers["cache-control"] == "no-store" and "raw_evidence" not in r.text


@then("an official Operator MCP read returns the same observer contract with no raw evidence")
def live_mcp_observer(c):
    from mcp import ClientSession
    from mcp.client.streamable_http import streamable_http_client

    async def run():
        async with streamable_http_client("http://127.0.0.1:19000/mcp") as (read, write, _):
            async with ClientSession(read, write) as session:
                await session.initialize()
                value = await session.call_tool(
                    "get_evidence",
                    {
                        "kind": "observer",
                        "scope": "node",
                        "node_id": "p1",
                        "observation": "routing",
                    },
                )
                assert not value.isError, value
                data = value.structuredContent["data"]
                assert data["records"] and data["window_seconds"] == 60
                assert (
                    value.structuredContent["raw_evidence"] == ""
                    and json.loads(value.content[0].text) == value.structuredContent
                )

    asyncio.run(run())


@then(
    "the host socket directory contains only a Unix socket and the observer process cannot swap or dump core"
)
def live_no_files(c):
    import subprocess

    directory = ROOT / "runtime/observer-socket"
    assert {p.name for p in directory.iterdir()} == {"counters.sock"} and (
        directory / "counters.sock"
    ).is_socket()
    properties = subprocess.check_output(
        [
            "systemctl",
            "--user",
            "show",
            "minicore-observer.service",
            "-p",
            "MemorySwapMax",
            "-p",
            "LimitCORE",
        ],
        text=True,
    )
    assert "MemorySwapMax=0" in properties and "LimitCORE=0" in properties, properties


@given("the IGMP-only host observer is enabled")
def capture_live_ready(c):
    import subprocess
    import time

    import httpx

    value = subprocess.check_output(
        ["systemctl", "is-active", "minicore-observer-capture.service"], text=True
    ).strip()
    assert value == "active"
    deadline = time.monotonic() + 25
    while time.monotonic() < deadline:
        r = httpx.get(
            "http://127.0.0.1:19000/api/v1/observer?scope=node&node_id=ce1&kind=igmp", timeout=5
        ).json()
        if r.get("source_health") == "ok":
            return
        time.sleep(1)
    raise AssertionError(r)


@when("an inventoried router transmits a synthetic IGMPv2 report")
def live_report(c):
    import subprocess

    # Synthetic 8-byte control message. No file/PCAP and no membership inferred.
    script = "import socket,struct;data=bytearray.fromhex('16000000ef4d0101');n=sum(struct.unpack('!4H',data));n=(n&65535)+(n>>16);n=(n&65535)+(n>>16);data[2:4]=struct.pack('!H',(~n)&65535);s=socket.socket(socket.AF_INET,socket.SOCK_RAW,socket.IPPROTO_IGMP);s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,b'to-host1\\0');s.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton('10.200.8.3'));s.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_TTL,1);s.sendto(data,('239.77.1.1',0));s.close()"
    result = subprocess.run(
        ["docker", "exec", "minicore-ce1-1", "python3", "-c", script],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stderr


@then("the scoped observer API reports the group and sending interface without raw bytes")
def live_report_found(c):
    import time

    import httpx

    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        r = httpx.get(
            "http://127.0.0.1:19000/api/v1/observer?scope=link&link_id=host1-ce1&kind=igmp",
            timeout=5,
        )
        value = r.json()
        records = [
            row for row in value.get("records", []) if row["data"].get("group") == "239.77.1.1"
        ]
        if records:
            c.igmp_acquired = records[0]["acquired_monotonic"]
            assert (
                records[0]["data"]["node_id"] == "ce1"
                and records[0]["data"]["interface"] == "to-host1"
            )
            assert "raw_evidence" not in r.text and "payload" not in r.text
            return
        time.sleep(0.5)
    raise AssertionError(value)


@then("the observation expires after sixty seconds even when read repeatedly")
def live_igmp_expires(c):
    import time

    import httpx

    deadline = time.monotonic() + 66
    while time.monotonic() < deadline:
        value = httpx.get(
            "http://127.0.0.1:19000/api/v1/observer?scope=node&node_id=ce1&kind=igmp", timeout=5
        ).json()
        matches = [
            row for row in value.get("records", []) if row["acquired_monotonic"] == c.igmp_acquired
        ]
        if time.monotonic() - c.igmp_acquired >= 60:
            assert not matches, value
            return
        time.sleep(3)
    raise AssertionError("expiry deadline not observed")


@then("the capture process is non-root with only CAP_NET_RAW and no swap or core dumps")
def capture_privileges(c):
    import subprocess

    pid = subprocess.check_output(
        ["systemctl", "show", "minicore-observer-capture.service", "-p", "MainPID", "--value"],
        text=True,
    ).strip()
    status = Path("/proc/" + pid + "/status").read_text()
    fields = dict(line.split(":", 1) for line in status.splitlines() if ":" in line)
    assert fields["Uid"].split()[0] == "1000" and int(fields["CapEff"].strip(), 16) == 1 << 13, (
        status
    )
    properties = subprocess.check_output(
        [
            "systemctl",
            "show",
            "minicore-observer-capture.service",
            "-p",
            "MemorySwapMax",
            "-p",
            "LimitCORE",
            "-p",
            "NoNewPrivileges",
        ],
        text=True,
    )
    assert (
        "MemorySwapMax=0" in properties
        and "LimitCORE=0" in properties
        and "NoNewPrivileges=yes" in properties
    ), properties


@when("a temporary identical filtered tap receives synthetic UDP OSPF and IGMP")
def kernel_filter_live(c):
    import subprocess

    script = r"""
import asyncio,json,struct,socket
from pathlib import Path
from minicore_mcp.observer_host import collect_interfaces
from minicore_mcp.igmp_capture import open_tap
async def run():
 inv=json.loads(Path('inventory/topology.json').read_text());values=await collect_interfaces(inv)
 interface=next(m['host_name'] for m in values['ce1']['_internal']['mappings'] if m['interface']=='to-host1')
 tap=open_tap(interface)
 try:
  code="import socket,struct;d=bytearray.fromhex('16000000ef4d0202');n=sum(struct.unpack('!4H',d));n=(n&65535)+(n>>16);n=(n&65535)+(n>>16);d[2:4]=struct.pack('!H',(~n)&65535);[(lambda s,p:(s.setsockopt(socket.SOL_SOCKET,socket.SO_BINDTODEVICE,b'to-host1\\0'),s.setsockopt(socket.IPPROTO_IP,socket.IP_MULTICAST_IF,socket.inet_aton('10.200.8.3')),s.sendto(d,('239.77.2.2',0)),s.close()))(socket.socket(socket.AF_INET,socket.SOCK_RAW,p),p) for p in [17,89,2]]"
  proc=await asyncio.create_subprocess_exec('docker','exec','minicore-ce1-1','python3','-c',code,stdout=asyncio.subprocess.DEVNULL,stderr=asyncio.subprocess.PIPE)
  _,err=await proc.communicate();assert proc.returncode==0,err
  protocols=[];deadline=asyncio.get_running_loop().time()+2
  while asyncio.get_running_loop().time()<deadline:
   try:
    data,_,_,_=tap.recvmsg(2048,256)
    if len(data)>34 and data[30:34]==bytes([239,77,2,2]):protocols.append(data[23])
   except BlockingIOError:await asyncio.sleep(.02)
  print(json.dumps(protocols))
 finally:tap.close()
asyncio.run(run())
"""
    result = subprocess.run(
        ["sudo", "env", "PYTHONPATH=mcp-service/src", "python3", "-"],
        input=script,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr
    c.kernel_protocols = json.loads(result.stdout)


@then("only the IGMP transmission is delivered by the kernel")
def only_kernel_igmp(c):
    assert c.kernel_protocols == [2], c.kernel_protocols
