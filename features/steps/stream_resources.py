import json
import socket
import time

from behave import then, when
from mcp_harness.wire import Wire


def start(c):
    c.resource_wire = Wire()
    c.add_cleanup(c.resource_wire.close)
    return c.resource_wire


def stream_socket(c, transport, burst=False):
    w = start(c)
    session, _ = w.initialize()
    path = (
        "/fixture/burst"
        if burst and transport == "auxiliary"
        else "/api/v1/activity/events"
        if transport == "auxiliary"
        else "/mcp"
    )
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, 4096)
    sock.settimeout(3)
    sock.connect(("127.0.0.1", w.port))
    payload = f"GET {path} HTTP/1.1\r\nHost: 127.0.0.1:{w.port}\r\nAuthorization: Bearer {w.tokens['operator']}\r\nMCP-Protocol-Version: 2025-03-26\r\nMcp-Session-Id: {session}\r\nAccept: text/event-stream\r\n\r\n"
    sock.sendall(payload.encode())
    header = b""
    while b"\r\n\r\n" not in header:
        header += sock.recv(1)
    assert header.startswith(b"HTTP/1.1 200"), header
    c.add_cleanup(sock.close)
    return w, sock


def status(w):
    result = w.request("GET", "/fixture/status")
    assert result[0] == 200
    return result[2]


def wait_released(c, seconds):
    w = c.resource_wire
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        value = status(w)
        if all(value[k] == 0 for k in ["aux", "burst", "mcp", "activity"]):
            return value
        time.sleep(0.15)
    raise AssertionError(f"resources remain: {value}")


@when('an independent client disconnects from a "{transport}" event stream')
def disconnect_stream(c, transport):
    w, sock = stream_socket(c, transport)
    sock.close()


@then("the stream resources are released and management remains responsive")
def released(c):
    wait_released(c, 6)


@when('an independent "{transport}" client stops reading a bounded event burst')
def slow_reader(c, transport):
    w, c.slow_socket = stream_socket(c, transport, True)
    if transport == "mcp":
        assert w.request("GET", "/fixture/fill-mcp")[0] == 200
    time.sleep(0.4)
    value = status(w)
    assert value["burst"] + value["mcp"] > 0, value


@then("backpressure closes the writer within its drain deadline without blocking management")
def deadline(c):
    wait_released(c, 13)
    c.slow_socket.close()


@when("an independent client disconnects after submitting a delayed diagnostic")
def vanished_post(c):
    w = start(c)
    session, _ = w.initialize()
    body = json.dumps(
        {
            "jsonrpc": "2.0",
            "id": 91,
            "method": "tools/call",
            "params": {"name": "get_routes", "arguments": {"node_id": "p1"}},
        }
    ).encode()
    with socket.create_connection(("127.0.0.1", w.port), timeout=3) as sock:
        headers = f"POST /mcp HTTP/1.1\r\nHost: 127.0.0.1:{w.port}\r\nAuthorization: Bearer {w.tokens['operator']}\r\nMCP-Protocol-Version: 2025-03-26\r\nMcp-Session-Id: {session}\r\nAccept: application/json\r\nContent-Type: application/json\r\nContent-Length: {len(body)}\r\n\r\n".encode()
        sock.sendall(headers + body)
    c.vanished_session = session


@then("the bounded diagnostic finishes and releases its activity and request registration")
def vanished_bounded(c):
    time.sleep(1.2)
    wait_released(c, 3)
    # Reusing the same typed ID must not hit a leaked duplicate-request registry.
    result = c.resource_wire.call("get_routes", session=c.vanished_session, request_id=91)
    assert result[0] == 200 and "result" in result[2], result
