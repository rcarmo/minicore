import io
import json
import runpy
from pathlib import Path
from unittest.mock import patch

from behave import then, when


def exercise(c, mode):
    clock = [0.0]
    c.smoke_connections = []
    c.smoke_pages = 0
    c.smoke_sleeps = 0

    class Response(io.BytesIO):
        def __init__(self, status, body):
            super().__init__(body)
            self.status = status

    class Connection:
        def __init__(self, *args, **kwargs):
            self.closed = False
            self.timeout = kwargs.get("timeout")
            c.smoke_connections.append(self)

        def request(self, method, path):
            self.path = path

        def getresponse(self):
            if self.path.endswith("/events"):
                return Response(200, b"event: logs.snapshot\n\nevent: logs.changed\n\n")
            c.smoke_pages += 1
            if mode == "recover" and c.smoke_pages > 1:
                return Response(
                    200,
                    json.dumps(
                        {
                            "data": {"entries": [{}, {}], "next_cursor": "older"},
                            "collected_at": "2026-09-26T00:00:00Z",
                            "error_code": None,
                        }
                    ).encode(),
                )
            return Response(
                503,
                json.dumps(
                    {
                        "error_code": "invalid_log_snapshot"
                        if mode == "invalid"
                        else "node_unavailable"
                    }
                ).encode(),
            )

        def close(self):
            self.closed = True

    def sleep(seconds):
        c.smoke_sleeps += 1
        clock[0] += seconds
        assert clock[0] <= 31, "unbounded smoke retry"

    c.smoke_error = None
    with (
        patch("http.client.HTTPConnection", Connection),
        patch("time.monotonic", side_effect=lambda: clock[0]),
        patch("time.sleep", side_effect=sleep),
    ):
        try:
            runpy.run_path(str(Path(__file__).resolve().parents[2] / "tests/logs_smoke.py"))
        except AssertionError as exc:
            c.smoke_error = exc
    c.smoke_elapsed = clock[0]


@when("the log smoke sees a restart invalidation before a fresh page")
def smoke_recovery(c):
    exercise(c, "recover")


@then("it waits for fresh bounded evidence and closes its connections")
def smoke_waited(c):
    assert c.smoke_error is None, c.smoke_error
    assert c.smoke_pages == 2 and c.smoke_sleeps == 1
    assert all(conn.closed for conn in c.smoke_connections)


@when("the log smoke receives unavailable pages until its deadline")
def smoke_failure(c):
    exercise(c, "unavailable")


@then("it fails within the deadline and closes its connections")
def smoke_deadline(c):
    assert c.smoke_error is not None
    assert 20 <= c.smoke_elapsed <= 31 and c.smoke_pages <= 61
    assert all(conn.closed for conn in c.smoke_connections)


@when("the log smoke receives a malformed snapshot error")
def smoke_invalid(c):
    exercise(c, "invalid")


@then("it rejects that page without retrying")
def smoke_rejected(c):
    assert c.smoke_error is not None and c.smoke_pages == 1 and c.smoke_sleeps == 0
    assert all(conn.closed for conn in c.smoke_connections)
