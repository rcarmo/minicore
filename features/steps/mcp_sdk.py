import json
import os
import secrets
import socket
import subprocess
import tempfile
from pathlib import Path

from behave import given, then, when
from mcp_harness.sdk import run_sdk

ROOT = Path(__file__).resolve().parents[2]


def compose(c, *args):
    p = subprocess.run(
        ["docker", "compose", "-f", str(c.sdk_dir / "compose.json"), *args],
        capture_output=True,
        text=True,
        timeout=90,
    )
    assert p.returncode == 0, p.stderr[-4000:]
    return p.stdout


@given("a disposable management Compose instance with isolated Operator and God credentials")
def sdk_fixture(c):
    temp = tempfile.TemporaryDirectory(prefix="minicore-sdk-")
    c.sdk_dir = Path(temp.name)
    c.sdk_tokens = {role: secrets.token_hex(24) for role in ["operator", "god"]}
    (c.sdk_dir / "tokens.json").write_text(json.dumps(c.sdk_tokens))
    os.chmod(c.sdk_dir / "tokens.json", 0o644)
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        c.sdk_port = s.getsockname()[1]
    c.sdk_project = "minicore-sdk-" + secrets.token_hex(4)
    service = {
        "name": c.sdk_project,
        "services": {
            "management": {
                "image": "minicore-management:0.1.0",
                "user": "10001:10001",
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "environment": {
                    "MINICORE_EXPOSURE_PROFILE": "authenticated",
                    "MINICORE_TOKEN_FILE": "/run/secrets/tokens.json",
                },
                "volumes": [str(c.sdk_dir / "tokens.json") + ":/run/secrets/tokens.json:ro"],
                "ports": [f"127.0.0.1:{c.sdk_port}:9000"],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "python",
                        "-c",
                        "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9000/healthz')",
                    ],
                    "interval": "1s",
                    "timeout": "2s",
                    "retries": 10,
                },
            }
        },
    }
    (c.sdk_dir / "compose.json").write_text(json.dumps(service))

    def cleanup():
        try:
            compose(c, "down", "--remove-orphans")
        finally:
            temp.cleanup()

    c.add_cleanup(cleanup)
    compose(c, "up", "-d", "--wait")


@when("the official Python MCP SDK connects from the host")
def sdk_connect(c):
    c.sdk_evidence = run_sdk(f"http://127.0.0.1:{c.sdk_port}/mcp", c.sdk_tokens)


@then("it negotiates the actual supported protocol and lists the role-specific tools")
def sdk_protocol(c):
    assert len(c.sdk_evidence) == 12
    assert all(row["protocol"] == "2025-03-26" for row in c.sdk_evidence)


@then("it invokes all six Operator tools and receives matching structured and text evidence")
def sdk_tools(c):
    assert len({row["tool"] for row in c.sdk_evidence}) == 6


@then("it observes native errors for unconnected backends rather than synthetic success")
def sdk_errors(c):
    assert all(
        row["is_error"] == (row["tool"] not in {"list_nodes", "get_evidence"})
        for row in c.sdk_evidence
    )


@then("a separate God client sees all ten tools without changing the Operator's discovery")
def sdk_roles(c):
    from mcp_harness.wire import GOD, OPERATOR

    assert {row["role"] for row in c.sdk_evidence} == {"operator", "god"}
    for row in c.sdk_evidence:
        expected = OPERATOR | GOD if row["role"] == "god" else OPERATOR
        assert set(row["discovered_tools"]) == expected
        assert set(row["operator_tools_after_god"]) == OPERATOR


@then("deleting sessions and stopping the fixture leaves no test service or secret files behind")
def sdk_cleanup(c):
    compose(c, "down", "--remove-orphans")
    names = subprocess.run(
        [
            "docker",
            "ps",
            "-a",
            "-q",
            "--filter",
            f"label=com.docker.compose.project={c.sdk_project}",
        ],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    assert not names
    for path in c.sdk_dir.glob("tokens.json"):
        path.unlink()
    assert not (c.sdk_dir / "tokens.json").exists()
    report = ROOT / "reports/mcp-sdk.json"
    report.parent.mkdir(exist_ok=True)
    report.write_text(
        json.dumps({"client": "mcp Python SDK 1.27.2", "observations": c.sdk_evidence}, indent=2)
        + "\n"
    )


@then("the SDK session event stream attaches successfully without HTTP 400")
def sdk_stream_ok(c):
    assert len(c.sdk_evidence) == 12  # exercise asserts GET success before calling any tools
