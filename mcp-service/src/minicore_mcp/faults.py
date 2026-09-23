"""Three fixed scenarios, one active fault and durable fail-closed recovery state."""

import asyncio
import copy
import json
import os
from datetime import datetime, timezone

SCENARIOS = {
    "core-link-failure": {"node_id": "p1", "interface": "to-p2", "parameters": {}},
    "customer-bgp-failure": {"node_id": "ce1", "interface": "to-pe1", "parameters": {}},
    "data-path-degradation": {
        "node_id": "ce1",
        "interface": "to-host1",
        "parameters": {"delay_ms": 100, "loss_percent": 10},
    },
}


class FaultController:
    def __init__(self, topology, executor, directory):
        self.topology = topology
        self.executor = executor
        self.directory = directory
        self.lock = asyncio.Lock()
        self.state = {
            "state": "baseline",
            "verified": False,
            "generation": topology.inventory["generation"],
            "scenario_id": None,
            "results": {},
            "audit": [],
        }
        file = directory / "state.json"
        if file.exists():
            try:
                if file.stat().st_size > 1024 * 1024:
                    raise ValueError()
                loaded = json.loads(file.read_text())
                if (
                    not isinstance(loaded, dict)
                    or type(loaded.get("generation")) is not int
                    or loaded["generation"] < topology.inventory["generation"]
                    or loaded.get("state")
                    not in {
                        "baseline",
                        "applying",
                        "active",
                        "resetting",
                        "reconciliation_required",
                    }
                    or type(loaded.get("verified")) is not bool
                    or loaded.get("scenario_id") not in {None, *SCENARIOS}
                    or not isinstance(loaded.get("results"), dict)
                    or len(loaded["results"]) > 128
                    or not isinstance(loaded.get("audit"), list)
                    or len(loaded["audit"]) > 128
                    or any(
                        not isinstance(v, dict)
                        or not {"operation", "scenario", "response"} <= set(v)
                        for v in loaded["results"].values()
                    )
                ):
                    raise ValueError()
                self.state = loaded
                if self.state["state"] != "baseline":
                    self.state["state"] = "reconciliation_required"
            except (ValueError, OSError, KeyError, TypeError):
                self.state["state"] = "reconciliation_required"
                self.state["error_code"] = "corrupt_state"
        self.topology.inventory["generation"] = self.state["generation"]

    def get_state(self):
        return {k: copy.deepcopy(v) for k, v in self.state.items() if k not in {"results", "audit"}}

    def save(self):
        self.directory.mkdir(parents=True, exist_ok=True)
        file = self.directory / "state.json"
        temp = self.directory / "state.tmp"
        with temp.open("w") as handle:
            json.dump(self.state, handle)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        os.replace(temp, file)
        generation = self.directory / "generation.tmp"
        generation.write_text(json.dumps({"generation": self.state["generation"]}))
        os.chmod(generation, 0o644)
        os.replace(generation, self.directory / "generation.json")
        directory = os.open(self.directory, os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)

    def response(self, error=None):
        return {"error_code": error, "data": self.get_state()}

    def replay(self, operation, scenario, key):
        previous = self.state["results"].get(key)
        if previous is None:
            return None
        if previous["operation"] != operation or previous["scenario"] != scenario:
            return self.response("idempotency_conflict")
        return copy.deepcopy(previous["response"])

    def record(self, operation, scenario, key, principal, error):
        self.state["audit"].append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "principal": principal,
                "operation": operation,
                "scenario_id": scenario,
                "request_key": key,
                "outcome": error or self.state["state"],
            }
        )
        self.state["audit"] = self.state["audit"][-128:]
        result = self.response(error)
        self.state["results"][key] = {
            "operation": operation,
            "scenario": scenario,
            "response": result,
        }
        # 128 retained idempotency records. Keys outside this window are not retry-safe.
        while len(self.state["results"]) > 128:
            self.state["results"].pop(next(iter(self.state["results"])))
        self.save()
        return result

    async def apply(self, scenario, key, principal):
        if scenario not in SCENARIOS:
            return self.response("unknown_scenario")
        if self.lock.locked():
            return self.response("mutation_in_progress")
        async with self.lock:
            previous = self.replay("apply", scenario, key)
            if previous is not None:
                return previous
            if self.state["state"] == "active":
                return self.response("fault_conflict")
            if self.state["state"] != "baseline":
                return self.response("reconciliation_required")
            try:
                if not await self.executor.verify_baseline():
                    return self.response("baseline_unverified")
                self.state.update(
                    state="applying", scenario_id=scenario, verified=False, **SCENARIOS[scenario]
                )
                self.save()
            except OSError:
                return self.response("persistence_failed")
            try:
                result = await self.executor.mutate(scenario, "apply")
                if not result.get("ok") or not result.get("verified"):
                    raise RuntimeError("verification_failed")
                self.state.update(state="active", verified=True, error_code=None)
                return self.record("apply", scenario, key, principal, None)
            except asyncio.CancelledError:
                self.state.update(
                    state="reconciliation_required", verified=False, error_code="interrupted"
                )
                self.save()
                raise
            except Exception:
                try:
                    rollback = await self.executor.mutate(scenario, "reset")
                    good = rollback.get("ok") and await self.executor.verify_baseline()
                except Exception:
                    good = False
                self.state.update(
                    state="baseline" if good else "reconciliation_required",
                    verified=bool(good),
                    error_code="apply_failed",
                )
                try:
                    return self.record("apply", scenario, key, principal, "apply_failed")
                except OSError:
                    return self.response("persistence_failed")

    async def reset(self, key, principal):
        if self.lock.locked():
            return self.response("mutation_in_progress")
        async with self.lock:
            previous = self.replay("reset", None, key)
            if previous is not None:
                return previous
            scenario = self.state.get("scenario_id")
            was_baseline = self.state["state"] == "baseline"
            old_generation = self.state["generation"]
            if (
                was_baseline
                and self.state.get("verified")
                and await self.executor.verify_baseline()
            ):
                try:
                    return self.record("reset", None, key, principal, None)
                except OSError:
                    return self.response("persistence_failed")
            try:
                self.state.update(state="resetting", verified=False)
                self.save()
            except OSError:
                return self.response("persistence_failed")
            try:
                # On corrupt/uncertain state remove only the three predefined Minicore effects.
                for target in [scenario] if scenario in SCENARIOS else list(SCENARIOS):
                    response = await self.executor.mutate(target, "reset")
                    if not response.get("ok"):
                        raise RuntimeError("reset failed")
                if not await self.executor.verify_baseline():
                    raise RuntimeError("baseline failed")
                self.state.update(
                    state="baseline", scenario_id=None, verified=True, error_code=None
                )
                for k in ["node_id", "interface", "parameters"]:
                    self.state.pop(k, None)
                if not was_baseline:
                    self.state["generation"] += 1
                response = self.record("reset", None, key, principal, None)
                self.topology.inventory["generation"] = self.state["generation"]
                return response
            except asyncio.CancelledError:
                self.state.update(
                    state="reconciliation_required", verified=False, error_code="interrupted"
                )
                self.save()
                raise
            except Exception:
                self.state["generation"] = old_generation
                self.state["results"].pop(key, None)
                self.state.update(
                    state="reconciliation_required", verified=False, error_code="reset_failed"
                )
                try:
                    return self.record("reset", None, key, principal, "reset_failed")
                except OSError:
                    return self.response("persistence_failed")
