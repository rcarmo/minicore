import json
import tempfile
from pathlib import Path

from minicore_mcp.logs import LogStore
from minicore_mcp.model import Topology
from minicore_mcp.policy import Policy
from minicore_mcp.server import Server

ROOT = Path(__file__).resolve().parents[1]


def before_scenario(context, scenario):
    context.temp = tempfile.TemporaryDirectory()
    context.root = Path(context.temp.name)
    context.tokens = context.root / "tokens.json"
    context.tokens.write_text(json.dumps({"operator": "o" * 40, "god": "g" * 40}))
    context.policy = Policy("authenticated", context.tokens)
    context.inventory_path = ROOT / "inventory/topology.json"
    context.inventory = json.loads(context.inventory_path.read_text())
    context.topology = Topology(context.inventory_path, context.root / "observations.json")
    context.store = LogStore(context.topology, ["configured-credential"])
    context.store.root.mkdir()
    context.logfile = context.store.root / "p1.json"
    context.server = Server(context.topology, context.policy, ROOT / "web-ui/dist")
    context.server.log_store = context.store
    context.generation = context.inventory["generation"]
    context.stream = None
    context.wire = None


def after_scenario(context, scenario):
    import asyncio

    if context.stream:
        runner = getattr(context, "stream_runner", None)
        if runner:
            runner.run(context.stream.aclose())
            runner.close()
        else:
            asyncio.run(context.stream.aclose())
    if context.wire:
        context.wire.tearDownClass()
    context.temp.cleanup()
