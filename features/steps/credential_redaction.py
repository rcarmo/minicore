import asyncio
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from behave import given, then, when
from umcp_shared import MCPRequestContext


def evidence(c, text):
    stamp = datetime.now(timezone.utc)
    c.logfile.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "source": "container",
                "error_code": None,
                "truncated": False,
                "lab_id": c.inventory["lab_id"],
                "generation": c.generation,
                "node_id": "p1",
                "collected_at": stamp.isoformat(),
                "window_start": (stamp - timedelta(minutes=15)).isoformat(),
                "status": "ok",
                "entries": [
                    {
                        "id": "a" * 24,
                        "timestamp": stamp.isoformat(),
                        "source": "container",
                        "severity": "info",
                        "message": "diagnostic text " + text,
                        "truncated": False,
                    }
                ],
            }
        )
    )
    directory = c.server.config_root / "p1"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "frr.conf").write_text("! diagnostic text " + text + "\n")


def replace_token(c, token):
    temp = c.tokens.with_suffix(".new")
    temp.write_text(json.dumps({"operator": token, "god": "g" * 40}))
    temp.replace(c.tokens)


async def read_evidence(c, surface, token):
    headers = {"authorization": "Bearer " + token}
    kind = "configuration" if "configuration" in surface else "logs"
    if surface.startswith("HTTP"):
        response = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/nodes/p1/" + ("config/frr.conf" if kind == "configuration" else "logs"),
            headers=headers,
            body=b"",
            peer="127.0.0.1",
        )
        return response.status, json.loads(response.body)
    args = {"kind": kind, "node_id": "p1"}
    if kind == "configuration":
        args["file"] = "frr.conf"
    response = await c.server.process_request_async(
        json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 41,
                "method": "tools/call",
                "params": {"name": "get_evidence", "arguments": args},
            }
        ),
        context=MCPRequestContext(transport="streamable-http", headers=headers),
    )
    result = response["result"]
    assert json.loads(result["content"][0]["text"]) == result["structuredContent"]
    return (503 if result["isError"] else 200), result["structuredContent"]


@given("evidence contains the current token as ordinary text")
def ordinary_token(c):
    c.server.config_root = c.root / "redaction-configs"
    c.old_token = "o" * 40
    c.new_token = "n" * 40
    evidence(c, c.old_token)


@when('the Operator credential rotates and evidence is read through "{surface}"')
def rotate_read(c, surface):
    async def run():
        replace_token(c, c.new_token)
        c.rotation_response = await read_evidence(c, surface, c.new_token)
        c.new_principal = c.policy.authenticate_cached({"authorization": "Bearer " + c.new_token})
        c.old_principal = c.policy.authenticate_cached({"authorization": "Bearer " + c.old_token})

    asyncio.run(run())


@then("only the new credential authenticates")
@then("the credential change still revokes the old identity")
def rotated_auth(c):
    assert c.new_principal is not None and c.new_principal.roles == ("operator",)
    assert c.old_principal is None


@then("the evidence succeeds without exposing the retired token")
def retired_hidden(c):
    status, payload = c.rotation_response
    assert status == 200, payload
    assert c.old_token not in json.dumps(payload), "retired token exposed"
    assert "REDACTED" in json.dumps(payload)


@when('"{source}" collection overlaps credential rotation')
def overlap_rotation(c, source):
    async def run():
        original = c.server.files.run
        evidence(c, c.old_token + " " + c.new_token)

        async def rotate_after_read(function, *args, **kwargs):
            result = await original(function, *args, **kwargs)
            replace_token(c, c.new_token)
            await c.policy.authenticate_async(
                {"authorization": "Bearer " + c.new_token}, c.server.auth_files
            )
            return result

        with patch.object(c.server.files, "run", side_effect=rotate_after_read):
            c.overlap_response = await read_evidence(c, "HTTP " + source, c.old_token)
        c.after_rotation = await read_evidence(c, "HTTP " + source, c.new_token)

    asyncio.run(run())


@then("the in-flight evidence is withheld with redaction_unavailable")
def overlap_hidden(c):
    status, payload = c.overlap_response
    assert status == 503 and payload["error_code"] == "redaction_unavailable", payload
    assert c.old_token not in json.dumps(payload) and c.new_token not in json.dumps(payload)


@then("a fresh request redacts both old and new credentials")
def fresh_redacts(c):
    status, payload = c.after_rotation
    assert status == 200
    assert c.old_token not in json.dumps(payload) and c.new_token not in json.dumps(payload)
    assert "REDACTED" in json.dumps(payload)


@when('credential rotation exceeds the redaction "{budget}" budget')
def redaction_capacity(c, budget):
    async def run():
        # Two roles start the history. Unique short tokens hit the 128-value cap;
        # large (but valid) credentials reach the 64-KiB byte budget first.
        for index in range(130 if budget == "count" else 7):
            c.new_token = f"rotation-{index:03d}-" + ("x" * (40 if budget == "count" else 11000))
            replace_token(c, c.new_token)
            c.new_principal = await c.policy.authenticate_async(
                {"authorization": "Bearer " + c.new_token}, c.server.auth_files
            )
        c.old_principal = c.policy.authenticate_cached({"authorization": "Bearer " + c.old_token})
        evidence(c, c.old_token)
        c.capacity_responses = [
            await read_evidence(c, surface, c.new_token)
            for surface in ("HTTP logs", "HTTP configuration", "MCP logs", "MCP configuration")
        ]
        c.capacity_topology = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/topology",
            headers={"authorization": "Bearer " + c.new_token},
            body=b"",
            peer="127.0.0.1",
        )

    asyncio.run(run())


@then("log and configuration evidence fail closed on HTTP and MCP")
def capacity_closed(c):
    for status, payload in c.capacity_responses:
        assert status == 503 and payload["error_code"] == "redaction_unavailable", payload
        assert c.old_token not in json.dumps(payload) and c.new_token not in json.dumps(payload)
    retained = c.policy.redaction_secrets
    assert len(retained) <= 128 and sum(len(s.encode()) for s in retained) <= 64 * 1024


@then("topology remains available with the new identity")
def capacity_inventory(c):
    assert c.capacity_topology.status == 200


@when("credential reload fails before a valid replacement is installed")
def invalid_then_replace(c):
    async def run():
        replace_token(c, c.new_token)
        await c.policy.authenticate_async(
            {"authorization": "Bearer " + c.new_token}, c.server.auth_files
        )
        c.tokens.write_text("{")
        assert await c.policy.authenticate_async({}, c.server.auth_files) is None
        replace_token(c, "z" * 40)
        evidence(c, c.old_token + " " + c.new_token)
        c.after_rotation = await read_evidence(c, "HTTP configuration", "z" * 40)

    asyncio.run(run())


@then("both current and replaced tokens stay redacted")
def invalid_redaction(c):
    fresh_redacts(c)


@when("a log event stream is opened with the new credential")
def redaction_stream(c):
    async def run():
        response = await c.server.handle_http_request_async(
            method="GET",
            path="/api/v1/nodes/p1/logs/events",
            headers={"authorization": "Bearer " + c.new_token},
            body=b"",
            peer="127.0.0.1",
        )
        assert response.status == 200
        try:
            c.redaction_event = (await anext(response.stream)).decode()
        finally:
            await response.stream.aclose()
        assert c.server.streams == 0

    asyncio.run(run())


@then("the stream reports unavailable redaction without evidence text")
def redaction_event(c):
    payload = json.loads(c.redaction_event.split("data: ", 1)[1].strip())
    assert payload["status"] == "unavailable" and payload["error_code"] == "redaction_unavailable"
    assert set(payload) == {"node_id", "generation", "revision", "status", "error_code"}
    assert c.old_token not in c.redaction_event and c.new_token not in c.redaction_event
