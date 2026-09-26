"""Bounded synchronous IGMP Ethernet/IPv4 parser."""

from __future__ import annotations

from ipaddress import IPv4Address

ETHERNET_HEADER_LENGTH = 14
ETHERTYPE_IPV4 = 0x0800
ETHERTYPE_VLAN = 0x8100
IPPROTO_IGMP = 2
IPV4_MIN_HEADER_LENGTH = 20
IGMP_V1_V2_LENGTH = 8
IGMP_V3_QUERY_MIN_LENGTH = 12
IGMP_V3_REPORT_MIN_LENGTH = 8
MAX_FRAME_LENGTH = 2048
MAX_IGMP_SOURCES = 64
MAX_IGMP_RECORDS = 64
VALID_V3_RECORD_TYPES = {1, 2, 3, 4, 5, 6}


class IGMPParseError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class UnsupportedChecksumOffloadError(IGMPParseError):
    def __init__(self):
        super().__init__("unsupported_checksum_offload")


class UnsupportedInputError(IGMPParseError):
    pass


class InvalidInputError(IGMPParseError):
    pass


def _checksum(data: bytes) -> int:
    if len(data) % 2:
        data += b"\x00"
    total = 0
    for index in range(0, len(data), 2):
        total += (data[index] << 8) + data[index + 1]
        total = (total & 0xFFFF) + (total >> 16)
    return (~total) & 0xFFFF


def _ipv4_text(raw: bytes) -> str:
    return str(IPv4Address(raw))


def _is_unicast(address: str) -> bool:
    ipv4 = IPv4Address(address)
    return not ipv4.is_multicast and int(ipv4) != 0x00000000


def _is_multicast_or_unspecified(address: str) -> bool:
    ipv4 = IPv4Address(address)
    return ipv4.is_multicast or int(ipv4) == 0


def _require_unicast(address: str, *, code: str = "invalid_unicast_address") -> None:
    if not _is_unicast(address):
        raise InvalidInputError(code)


def _require_group(address: str, *, allow_unspecified: bool = False) -> None:
    if allow_unspecified and address == "0.0.0.0":
        return
    if not IPv4Address(address).is_multicast:
        raise InvalidInputError("invalid_multicast_group")


def _require_checksum_policy(checksum_policy: str) -> None:
    if checksum_policy == "verified":
        return
    if checksum_policy in {"offloaded", "partial", "unsupported"}:
        raise UnsupportedChecksumOffloadError()
    raise UnsupportedInputError("unsupported_checksum_policy")


def parse_igmp_ethernet_frame(frame: bytes, *, checksum_policy: str) -> dict:
    _require_checksum_policy(checksum_policy)
    if len(frame) > MAX_FRAME_LENGTH:
        raise UnsupportedInputError("frame_too_large")
    if len(frame) < ETHERNET_HEADER_LENGTH + IPV4_MIN_HEADER_LENGTH:
        raise InvalidInputError("truncated_ethernet_frame")

    ethertype = int.from_bytes(frame[12:14], "big")
    if ethertype == ETHERTYPE_VLAN:
        raise UnsupportedInputError("unsupported_vlan_frame")
    if ethertype != ETHERTYPE_IPV4:
        raise UnsupportedInputError("unsupported_ethertype")

    packet = frame[ETHERNET_HEADER_LENGTH:]
    version_ihl = packet[0]
    if version_ihl >> 4 != 4:
        raise UnsupportedInputError("unsupported_ip_version")
    header_length = (version_ihl & 0x0F) * 4
    if header_length < IPV4_MIN_HEADER_LENGTH or len(packet) < header_length:
        raise InvalidInputError("truncated_ipv4_header")
    total_length = int.from_bytes(packet[2:4], "big")
    if total_length < header_length or len(packet) < total_length:
        raise InvalidInputError("truncated_ipv4_datagram")
    # Ethernet may pad a short IPv4 datagram to its minimum payload size.
    # Only the declared IP bytes belong to checksums and IGMP length checks.
    packet = packet[:total_length]
    if _checksum(packet[:header_length]) != 0:
        raise InvalidInputError("invalid_ipv4_checksum")
    if packet[9] != IPPROTO_IGMP:
        raise UnsupportedInputError("unsupported_ip_protocol")
    flags_fragment = int.from_bytes(packet[6:8], "big")
    if flags_fragment & 0x3FFF:
        raise UnsupportedInputError("fragmented_ipv4_datagram")

    source = _ipv4_text(packet[12:16])
    destination = _ipv4_text(packet[16:20])
    _require_unicast(source)
    _require_group(destination, allow_unspecified=False)

    igmp = packet[header_length:total_length]
    if len(igmp) < IGMP_V1_V2_LENGTH:
        raise InvalidInputError("truncated_igmp_message")
    if _checksum(igmp) != 0:
        raise InvalidInputError("invalid_igmp_checksum")

    msg_type = igmp[0]
    if msg_type == 0x11:
        return _parse_query(igmp, source)
    if msg_type == 0x12:
        group = _ipv4_text(igmp[4:8])
        _require_group(group)
        return _result(version=1, message_type="report_v1", reporter=source, group=group)
    if msg_type == 0x16:
        group = _ipv4_text(igmp[4:8])
        _require_group(group)
        return _result(version=2, message_type="report_v2", reporter=source, group=group)
    if msg_type == 0x17:
        group = _ipv4_text(igmp[4:8])
        _require_group(group)
        return _result(version=2, message_type="leave", reporter=source, group=group)
    if msg_type == 0x22:
        return _parse_v3_report(igmp, source)
    raise UnsupportedInputError("unsupported_igmp_type")


def _result(
    *,
    version: int,
    message_type: str,
    reporter: str | None = None,
    querier: str | None = None,
    group: str | None = None,
    sources: list[str] | None = None,
    records: list[dict] | None = None,
) -> dict:
    return {
        "version": version,
        "message_type": message_type,
        "group": group,
        "reporter": reporter,
        "querier": querier,
        "sources": sources if sources is not None else [],
        "records": records if records is not None else [],
    }


def _parse_query(igmp: bytes, source: str) -> dict:
    group = _ipv4_text(igmp[4:8])
    if len(igmp) == IGMP_V1_V2_LENGTH:
        version = 1 if igmp[1] == 0 else 2
        _require_group(group, allow_unspecified=True)
        return _result(
            version=version,
            message_type="query",
            querier=source,
            group=None if group == "0.0.0.0" else group,
        )

    if len(igmp) < IGMP_V3_QUERY_MIN_LENGTH:
        raise InvalidInputError("truncated_igmp_message")

    _require_group(group, allow_unspecified=True)
    source_count = int.from_bytes(igmp[10:12], "big")
    if source_count > MAX_IGMP_SOURCES:
        raise UnsupportedInputError("igmp_source_limit_exceeded")
    expected_length = IGMP_V3_QUERY_MIN_LENGTH + (source_count * 4)
    if len(igmp) != expected_length:
        raise InvalidInputError("truncated_igmp_message")
    sources = []
    offset = IGMP_V3_QUERY_MIN_LENGTH
    for _ in range(source_count):
        candidate = _ipv4_text(igmp[offset : offset + 4])
        _require_unicast(candidate)
        sources.append(candidate)
        offset += 4
    return _result(
        version=3,
        message_type="query",
        querier=source,
        group=None if group == "0.0.0.0" else group,
        sources=sources,
    )


def _parse_v3_report(igmp: bytes, source: str) -> dict:
    if len(igmp) < IGMP_V3_REPORT_MIN_LENGTH:
        raise InvalidInputError("truncated_igmp_message")
    record_count = int.from_bytes(igmp[6:8], "big")
    if record_count > MAX_IGMP_RECORDS:
        raise UnsupportedInputError("igmp_record_limit_exceeded")
    records = []
    offset = IGMP_V3_REPORT_MIN_LENGTH
    for _ in range(record_count):
        if len(igmp) < offset + 8:
            raise InvalidInputError("truncated_igmp_message")
        record_type = igmp[offset]
        if record_type not in VALID_V3_RECORD_TYPES:
            raise UnsupportedInputError("unsupported_igmpv3_record_type")
        aux_length = igmp[offset + 1]
        source_count = int.from_bytes(igmp[offset + 2 : offset + 4], "big")
        if source_count > MAX_IGMP_SOURCES:
            raise UnsupportedInputError("igmp_source_limit_exceeded")
        group = _ipv4_text(igmp[offset + 4 : offset + 8])
        _require_group(group)
        offset += 8
        expected_sources_end = offset + (source_count * 4)
        aux_bytes = aux_length * 4
        expected_end = expected_sources_end + aux_bytes
        if len(igmp) < expected_end:
            raise InvalidInputError("truncated_igmp_message")
        sources = []
        while offset < expected_sources_end:
            candidate = _ipv4_text(igmp[offset : offset + 4])
            _require_unicast(candidate)
            sources.append(candidate)
            offset += 4
        offset = expected_end
        records.append({"record_type": record_type, "group": group, "sources": sources})
    if offset != len(igmp):
        raise InvalidInputError("truncated_igmp_message")
    return _result(version=3, message_type="report_v3", reporter=source, records=records)
