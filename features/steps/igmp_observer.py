import importlib
from ipaddress import IPv4Address

from behave import given, then, when

ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_VLAN = 0x8100
IPPROTO_IGMP = 2
MAX_FRAME = 2048


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for index in range(0, len(data), 2):
        total += (data[index] << 8) + data[index + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _ipv4_bytes(address: str) -> bytes:
    return IPv4Address(address).packed


def _build_ipv4_packet(
    payload: bytes,
    *,
    source: str,
    destination: str,
    ttl: int = 1,
    fragment_offset: int = 0,
    more_fragments: bool = False,
    checksum_override: int | None = None,
    protocol: int = IPPROTO_IGMP,
) -> bytes:
    version_ihl = 0x45
    total_length = 20 + len(payload)
    flags_offset = fragment_offset & 0x1FFF
    if more_fragments:
        flags_offset |= 0x2000
    header = bytearray(
        [
            version_ihl,
            0,
            (total_length >> 8) & 0xFF,
            total_length & 0xFF,
            0,
            1,
            (flags_offset >> 8) & 0xFF,
            flags_offset & 0xFF,
            ttl,
            protocol,
            0,
            0,
            *_ipv4_bytes(source),
            *_ipv4_bytes(destination),
        ]
    )
    checksum = checksum_override if checksum_override is not None else _checksum(bytes(header))
    header[10] = (checksum >> 8) & 0xFF
    header[11] = checksum & 0xFF
    return bytes(header) + payload


def _build_ethernet_frame(
    payload: bytes, *, ethertype: int = ETHERTYPE_IPV4, trailing: bytes = b""
) -> bytes:
    return (
        bytes.fromhex("01005e000001 020000000001".replace(" ", ""))
        + ethertype.to_bytes(2, "big")
        + payload
        + trailing
    )


def _igmp_v1_v2(
    msg_type: int, group: str, *, max_resp: int = 0, checksum_override: int | None = None
) -> bytes:
    body = bytearray([msg_type, max_resp, 0, 0, *_ipv4_bytes(group)])
    checksum = checksum_override if checksum_override is not None else _checksum(bytes(body))
    body[2] = (checksum >> 8) & 0xFF
    body[3] = checksum & 0xFF
    return bytes(body)


def _igmp_v3_query(
    group: str, sources: list[str], *, max_resp: int = 100, qqic: int = 10, qrv: int = 2
) -> bytes:
    body = bytearray(
        [
            0x11,
            max_resp,
            0,
            0,
            *_ipv4_bytes(group),
            qrv & 0x07,
            qqic,
            (len(sources) >> 8) & 0xFF,
            len(sources) & 0xFF,
        ]
    )
    for source in sources:
        body.extend(_ipv4_bytes(source))
    checksum = _checksum(bytes(body))
    body[2] = (checksum >> 8) & 0xFF
    body[3] = checksum & 0xFF
    return bytes(body)


def _igmp_v3_report(records: list[dict]) -> bytes:
    body = bytearray([0x22, 0, 0, 0, 0, 0, (len(records) >> 8) & 0xFF, len(records) & 0xFF])
    for record in records:
        sources = record["sources"]
        body.extend(
            [
                record["record_type"],
                0,
                (len(sources) >> 8) & 0xFF,
                len(sources) & 0xFF,
                *_ipv4_bytes(record["group"]),
            ]
        )
        for source in sources:
            body.extend(_ipv4_bytes(source))
    checksum = _checksum(bytes(body))
    body[2] = (checksum >> 8) & 0xFF
    body[3] = checksum & 0xFF
    return bytes(body)


def _frame_for_message(message: str) -> bytes:
    match message:
        case "v1 query":
            igmp = _igmp_v1_v2(0x11, "0.0.0.0", max_resp=0)
            packet = _build_ipv4_packet(igmp, source="10.0.0.1", destination="224.0.0.1")
        case "v1 report":
            igmp = _igmp_v1_v2(0x12, "239.1.1.1")
            packet = _build_ipv4_packet(igmp, source="10.0.0.2", destination="239.1.1.1")
        case "v2 query":
            igmp = _igmp_v1_v2(0x11, "239.1.1.1", max_resp=10)
            packet = _build_ipv4_packet(igmp, source="10.0.0.1", destination="224.0.0.1")
        case "v2 report":
            igmp = _igmp_v1_v2(0x16, "239.1.1.1")
            packet = _build_ipv4_packet(igmp, source="10.0.0.2", destination="239.1.1.1")
        case "v2 leave":
            igmp = _igmp_v1_v2(0x17, "239.1.1.1")
            packet = _build_ipv4_packet(igmp, source="10.0.0.2", destination="224.0.0.2")
        case "v3 query":
            igmp = _igmp_v3_query("239.1.1.1", ["10.0.0.10", "10.0.0.11"])
            packet = _build_ipv4_packet(igmp, source="10.0.0.1", destination="224.0.0.1")
        case "v3 report":
            igmp = _igmp_v3_report(
                [
                    {"record_type": 1, "group": "239.1.1.1", "sources": ["10.0.0.10", "10.0.0.11"]},
                    {"record_type": 2, "group": "239.1.1.2", "sources": ["10.0.0.12"]},
                ]
            )
            packet = _build_ipv4_packet(igmp, source="10.0.0.2", destination="224.0.0.22", ttl=1)
        case _:
            raise AssertionError(message)
    return _build_ethernet_frame(packet)


def _frame_variant(variant: str) -> tuple[bytes, str]:
    if variant == "unpadded v2 report":
        return _frame_for_message("v2 report"), "v2 report"
    if variant == "padded minimum Ethernet zero trailing bytes":
        frame = _frame_for_message("v2 report")
        return frame + (b"\x00" * (60 - len(frame))), "v2 report"
    if variant == "padded minimum Ethernet nonzero trailing bytes":
        frame = _frame_for_message("v2 report")
        return frame + bytes(range(1, 60 - len(frame) + 1)), "v2 report"
    raise AssertionError(variant)


def _bad_frame(condition: str) -> tuple[bytes, str]:
    if condition == "invalid IPv4 checksum":
        frame = _build_ethernet_frame(
            _build_ipv4_packet(
                _igmp_v1_v2(0x16, "239.1.1.1"),
                source="10.0.0.2",
                destination="239.1.1.1",
                checksum_override=1,
            )
        )
    elif condition == "invalid IGMP checksum":
        frame = _build_ethernet_frame(
            _build_ipv4_packet(
                _igmp_v1_v2(0x16, "239.1.1.1", checksum_override=1),
                source="10.0.0.2",
                destination="239.1.1.1",
            )
        )
    elif condition == "fragmented datagram":
        frame = _build_ethernet_frame(
            _build_ipv4_packet(
                _igmp_v1_v2(0x16, "239.1.1.1"),
                source="10.0.0.2",
                destination="239.1.1.1",
                more_fragments=True,
            )
        )
    elif condition == "truncated frame":
        igmp = _igmp_v3_report(
            [
                {"record_type": 1, "group": "239.1.1.1", "sources": ["10.0.0.10", "10.0.0.11"]},
            ]
        )[:-4]
        igmp = bytearray(igmp)
        igmp[2] = 0
        igmp[3] = 0
        checksum = _checksum(bytes(igmp))
        igmp[2] = (checksum >> 8) & 0xFF
        igmp[3] = checksum & 0xFF
        frame = _build_ethernet_frame(
            _build_ipv4_packet(bytes(igmp), source="10.0.0.2", destination="224.0.0.22")
        )
    elif condition == "truncated by IPv4 total length despite padding":
        packet = _build_ipv4_packet(
            _igmp_v3_query("239.1.1.1", []),
            source="10.0.0.1",
            destination="224.0.0.1",
        )
        truncated = bytearray(packet)
        truncated[2] = 0
        truncated[3] = 24
        truncated[10] = 0
        truncated[11] = 0
        checksum = _checksum(bytes(truncated[:20]))
        truncated[10] = (checksum >> 8) & 0xFF
        truncated[11] = checksum & 0xFF
        frame = _build_ethernet_frame(bytes(truncated), trailing=b"\x00\x00\x00\x00")
    elif condition == "above snap length":
        frame = _frame_for_message("v2 report") + (
            b"\x00" * (MAX_FRAME + 1 - len(_frame_for_message("v2 report")))
        )
    elif condition == "unsupported VLAN frame":
        frame = _build_ethernet_frame(
            _build_ipv4_packet(
                _igmp_v1_v2(0x16, "239.1.1.1"), source="10.0.0.2", destination="239.1.1.1"
            ),
            ethertype=ETHERTYPE_VLAN,
        )
    elif condition == "excess v3 sources":
        frame = _build_ethernet_frame(
            _build_ipv4_packet(
                _igmp_v3_query("239.1.1.1", [f"10.0.0.{index}" for index in range(1, 66)]),
                source="10.0.0.1",
                destination="224.0.0.1",
            )
        )
    elif condition == "checksum offload":
        frame = _frame_for_message("v2 report")
    else:
        raise AssertionError(condition)
    return frame, condition


EXPECTED = {
    "v1 query": {
        "version": 1,
        "message_type": "query",
        "group": None,
        "reporter": None,
        "querier": "10.0.0.1",
        "sources": [],
        "records": [],
    },
    "v1 report": {
        "version": 1,
        "message_type": "report_v1",
        "group": "239.1.1.1",
        "reporter": "10.0.0.2",
        "querier": None,
        "sources": [],
        "records": [],
    },
    "v2 query": {
        "version": 2,
        "message_type": "query",
        "group": "239.1.1.1",
        "reporter": None,
        "querier": "10.0.0.1",
        "sources": [],
        "records": [],
    },
    "v2 report": {
        "version": 2,
        "message_type": "report_v2",
        "group": "239.1.1.1",
        "reporter": "10.0.0.2",
        "querier": None,
        "sources": [],
        "records": [],
    },
    "v2 leave": {
        "version": 2,
        "message_type": "leave",
        "group": "239.1.1.1",
        "reporter": "10.0.0.2",
        "querier": None,
        "sources": [],
        "records": [],
    },
    "v3 query": {
        "version": 3,
        "message_type": "query",
        "group": "239.1.1.1",
        "reporter": None,
        "querier": "10.0.0.1",
        "sources": ["10.0.0.10", "10.0.0.11"],
        "records": [],
    },
    "v3 report": {
        "version": 3,
        "message_type": "report_v3",
        "group": None,
        "reporter": "10.0.0.2",
        "querier": None,
        "sources": [],
        "records": [
            {"record_type": 1, "group": "239.1.1.1", "sources": ["10.0.0.10", "10.0.0.11"]},
            {"record_type": 2, "group": "239.1.1.2", "sources": ["10.0.0.12"]},
        ],
    },
}


def _ensure_parser(context):
    if getattr(context, "parser", None) is None and getattr(context, "import_error", None) is None:
        load_parser(context)


@when("the IGMP observer parser is loaded")
def load_parser(context):
    try:
        module = importlib.import_module("minicore_mcp.igmp")
    except ModuleNotFoundError as exc:
        context.import_error = exc
        context.parser = None
        return
    context.import_error = None
    context.parser = getattr(module, "parse_igmp_ethernet_frame", None)


@then("it exposes a synchronous bounded parser callable")
def parser_callable(context):
    assert context.import_error is None, context.import_error
    assert callable(context.parser)
    assert not context.parser.__code__.co_flags & 0x80


@given('a synthetic "{message}" Ethernet IPv4 IGMP frame')
def synthetic_frame(context, message):
    context.message = message
    context.frame = _frame_for_message(message)


@given('a synthetic IGMP frame variant "{variant}"')
def padded_frame(context, variant):
    context.frame, context.message = _frame_variant(variant)


@when("the parser decodes the frame with verified checksums")
def parse_verified(context):
    _ensure_parser(context)
    context.result = context.parser(context.frame, checksum_policy="verified")


@then('it returns the expected IGMP observation fields for "{message}"')
def verify_result(context, message):
    assert context.result == EXPECTED[message]


@given('a synthetic IGMP frame with condition "{condition}"')
def malformed_frame(context, condition):
    context.frame, context.condition = _bad_frame(condition)


@when("the parser validates the frame")
def parse_invalid(context):
    _ensure_parser(context)
    policy = "offloaded" if context.condition == "checksum offload" else "verified"
    try:
        context.parser(context.frame, checksum_policy=policy)
    except Exception as exc:  # parser-defined exception type checked by code field
        context.error = exc
    else:
        context.error = None


@then('it rejects the frame as "{reason}"')
def verify_error(context, reason):
    assert context.error is not None
    assert getattr(context.error, "code", None) == reason
