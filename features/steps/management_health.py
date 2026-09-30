import json
import subprocess
from pathlib import Path
from uuid import uuid4

from behave import given, then, when

ROOT = Path(__file__).resolve().parents[2]


@given("the management image and its generated health command")
def management_image(c):
    service = json.loads((ROOT / "compose/compose.json").read_text())["services"]["management"]
    c.health_image = service["image"]
    c.health_command = service["healthcheck"]["test"]
    assert c.health_command[:3] == ["CMD", "/bin/busybox", "wget"]
    assert service["healthcheck"]["timeout"] == "3s"


@when('the native probe encounters a "{listener}" loopback listener in an isolated container')
def isolated_probe(c, listener):
    name = "minicore-health-test-" + uuid4().hex[:12]
    c.probe_name = name
    c.probe_listener = listener
    source = (ROOT / "tests/health_probe_fixture.py").read_text()
    try:
        result = subprocess.run(
            [
                "docker",
                "run",
                "--rm",
                "--name",
                name,
                "--network",
                "none",
                "--user",
                "10001:10001",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--pids-limit",
                "16",
                "--memory",
                "64m",
                "--memory-swap",
                "64m",
                "--cpus",
                "1",
                "--entrypoint",
                "python",
                c.health_image,
                "-c",
                source,
                listener,
                json.dumps(c.health_command[1:]),
            ],
            capture_output=True,
            text=True,
            timeout=45,
        )
        assert result.returncode == 0, result.stderr
        c.probe_result = json.loads(result.stdout)
    finally:
        # Only this unique disposable fixture is eligible for cleanup.
        subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=15)


@then('its result is "{result}" within the probe deadline')
def correct_probe(c, result):
    measured = c.probe_result
    assert (measured["exit_code"] == 0) == (result == "healthy"), measured
    assert measured["elapsed"] < 3, measured
    assert measured["requests"] == (
        [] if c.probe_listener == "unavailable" else ["GET /healthz HTTP/1.1"]
    ), measured


@then("the fixture leaves no running container behind")
def probe_cleaned(c):
    result = subprocess.run(
        ["docker", "ps", "-aq", "--filter", "name=^/" + c.probe_name + "$"],
        capture_output=True,
        text=True,
        check=True,
        timeout=15,
    )
    assert not result.stdout.strip(), result.stdout
