"""Bounded, on-demand routing evidence shared by HTTP and Operator MCP."""

import asyncio
from datetime import datetime, timezone


def prefixes(topology):
    return [
        link["subnet"]
        for link in topology.inventory["links"]
        if any(topology.nodes[e["node"]]["kind"] == "endpoint" for e in link["endpoints"])
    ]


def declared(topology):
    nodes = topology.inventory["nodes"]
    provider = [n for n in nodes if n.get("asn") == 65000]
    peerings = []
    for index, a in enumerate(provider):
        for b in provider[index + 1 :]:
            peerings.append(
                {
                    "id": f"ibgp-{a['id']}-{b['id']}",
                    "source": a["id"],
                    "target": b["id"],
                    "source_address": a["loopback"].split("/")[0],
                    "target_address": b["loopback"].split("/")[0],
                    "kind": "iBGP",
                    "provenance": "declared_inventory",
                }
            )
    for link in topology.inventory["links"]:
        a, b = link["endpoints"]
        na, nb = topology.nodes[a["node"]], topology.nodes[b["node"]]
        if na.get("asn") and nb.get("asn") and na["asn"] != nb["asn"]:
            peerings.append(
                {
                    "id": f"ebgp-{link['id']}",
                    "source": a["node"],
                    "target": b["node"],
                    "source_address": a["address"].split("/")[0],
                    "target_address": b["address"].split("/")[0],
                    "kind": "eBGP",
                    "provenance": "declared_inventory",
                }
            )
    return peerings


def valid(data, prefix):
    return (
        isinstance(data, dict)
        and data.get("prefix") == prefix
        and all(
            isinstance(data.get(k), dict)
            for k in ("bgp", "rib", "bgp_peers", "ospf_neighbors", "received")
        )
        and all(isinstance(data.get(k), list) for k in ("fib", "advertised"))
        and data["bgp"].get("prefix") == prefix
        and isinstance(data["bgp"].get("paths"), list)
        and all(isinstance(path, dict) for path in data["bgp"]["paths"])
        and set(data["rib"]) <= {prefix}
        and all(
            isinstance(routes, list) and all(isinstance(route, dict) for route in routes)
            for routes in data["rib"].values()
        )
        and all(isinstance(route, dict) and route.get("dst") == prefix for route in data["fib"])
        and all(
            isinstance(ad, dict)
            and isinstance(ad.get("peer"), str)
            and type(ad.get("present")) is bool
            and ad.get("source") == "advertised_by_node"
            for ad in data["advertised"]
        )
        and data["received"].get("status") == "not_collected"
    )


async def collect(topology, adapter, prefix, activity=None):
    if prefix not in prefixes(topology):
        raise ValueError("invalid_prefix")
    generation = topology.inventory["generation"]

    async def node(n):
        result = topology.envelope("get_routing", n["id"], error="backend_not_configured")
        result.update(
            source="node_dispatcher",
            collected_at=datetime.now(timezone.utc).isoformat(),
            generation=generation,
        )
        active = activity.start(n["id"], generation) if activity and adapter else None
        try:
            if adapter:
                result.update(
                    await adapter.execute(n["id"], {"operation": "get_routing", "prefix": prefix})
                )
                if result["error_code"] is None and not valid(result["data"], prefix):
                    result.update(
                        status="unavailable", error_code="parse_failure", data=None, raw_evidence=""
                    )
        finally:
            if active:
                activity.finish(active)
        return result

    nodes = await asyncio.gather(
        *(node(n) for n in topology.inventory["nodes"] if n["kind"] == "router")
    )
    if generation != topology.inventory["generation"]:
        for result in nodes:
            result.update(
                status="unavailable", error_code="generation_changed", data=None, raw_evidence=""
            )
    count = sum(n["error_code"] is None for n in nodes)
    result = topology.envelope(
        "get_routing",
        data={
            "prefix": prefix,
            "nodes": nodes,
            "collected": count,
            "expected": len(nodes),
            "atomic": False,
            "stale_after_seconds": 30,
            "provenance": "on_demand_node_dispatcher",
        },
    )
    result.update(
        generation=generation,
        status="ok" if count == len(nodes) else "partial" if count else "unavailable",
        error_code=None if count else "collection_unavailable",
    )
    return result
