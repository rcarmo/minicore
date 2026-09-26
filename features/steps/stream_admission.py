import asyncio
import json
from unittest.mock import patch

from behave import then, when

PATHS = {
    "topology": "/api/v1/events",
    "logs": "/api/v1/nodes/p1/logs/events",
    "activity": "/api/v1/activity/events",
    "observer": "/api/v1/observer/events",
}


async def request(c, path, role="operator"):
    return await c.server.handle_http_request_async(
        method="GET",
        path=path,
        headers={"authorization": "Bearer " + role[0] * 40},
        body=b"",
        peer="127.0.0.1",
    )


@when('sixteen "{kind}" event responses are created without reading them')
def unstarted(c, kind):
    async def run():
        streams = [(await request(c, PATHS[kind])).stream for _ in range(16)]
        assert all(streams)
        c.limit_response = await request(c, "/api/v1/events")
        if c.limit_response.stream:
            await c.limit_response.stream.aclose()
        c.admitted_streams = c.server.streams
        # Unstarted async generators also need a close hook to release admission.
        await streams[0].aclose()
        await streams[0].aclose()
        c.after_unread_close = c.server.streams
        replacement = await request(c, PATHS[kind])
        c.replacement_status = replacement.status
        await anext(replacement.stream)
        c.after_started = c.server.streams
        await replacement.stream.aclose()
        await replacement.stream.aclose()
        for stream in streams[1:]:
            await stream.aclose()
        c.after_all_closed = c.server.streams

    asyncio.run(run())


@then("the next event request returns 503 stream_limit")
def limited(c):
    assert c.limit_response.status == 503, c.limit_response.status
    assert json.loads(c.limit_response.body) == {"error_code": "stream_limit"}
    assert c.admitted_streams == 16


@then("closing unread and started responses releases each slot exactly once")
def closed_once(c):
    assert c.after_unread_close == 15
    assert c.replacement_status == 200 and c.after_started == 16
    assert c.after_all_closed == 0


async def revoke_during_read(c, action):
    original = c.server.files.run
    did_revoke = False

    async def read_and_revoke(function, *args, **kwargs):
        nonlocal did_revoke
        result = await original(function, *args, **kwargs)
        if not did_revoke:
            did_revoke = True
            c.tokens.write_text(json.dumps({"operator": "x" * 40, "god": "y" * 40}))
        return result

    with patch.object(c.server.files, "run", side_effect=read_and_revoke):
        await action()
    assert did_revoke


@when('a "{kind}" event waits on collection while its credential is revoked')
def late_event(c, kind):
    async def run():
        response = await request(c, PATHS[kind])

        async def consume():
            try:
                c.late_event = await anext(response.stream)
            except StopAsyncIteration:
                c.late_event = None
            finally:
                await response.stream.aclose()

        await revoke_during_read(c, consume)
        c.late_stream_count = c.server.streams

    asyncio.run(run())


@then("it closes without emitting the pending event and releases its slot")
def no_late_event(c):
    assert c.late_event is None, c.late_event
    assert c.late_stream_count == 0


@when("a God topology response waits on collection while its credential is revoked")
def late_god(c):
    async def run():
        async def consume():
            c.late_god = await request(c, "/api/v1/topology?view=god", "god")

        await revoke_during_read(c, consume)

    asyncio.run(run())


@then("the HTTP response denies access without controller state")
def god_denied(c):
    assert c.late_god.status == 401, c.late_god.body
    assert "controller" not in c.late_god.body.decode()
