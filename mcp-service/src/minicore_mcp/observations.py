"""Bounded live sources for a single node inspector; browser reads are not agent activity."""

import asyncio
from datetime import datetime, timezone


async def collect(topology, adapter, node):
    generation = topology.inventory["generation"]
    protocols = topology.nodes[node]["protocols"]

    async def source(kind, request):
        result = topology.envelope(request["operation"], node, error="backend_not_configured")
        result.update(source="node_dispatcher", generation=generation)
        if kind != "interfaces" and kind not in protocols:
            result.update(error_code="protocol_not_enabled")
        elif adapter:
            result.update(await adapter.execute(node, request))
        result["collected_at"] = datetime.now(timezone.utc).isoformat()
        return kind, result

    rows = await asyncio.gather(
        source("interfaces", {"operation": "get_interfaces"}),
        source("bgp", {"operation": "get_neighbors", "protocol": "bgp"}),
        source("ospf", {"operation": "get_neighbors", "protocol": "ospf"}),
    )
    if topology.inventory["generation"] != generation:
        for _, result in rows:
            result.update(
                status="unavailable", error_code="generation_changed", data=None, raw_evidence=""
            )
    response = topology.envelope("node_observations", node, data=dict(rows))
    response["generation"] = generation
    return response
