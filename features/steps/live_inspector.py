import json

from behave import given, then


@given("the node adapter supplies interface and neighbor observations")
def inspector_adapter(c):
    class Adapter:
        def __init__(self):
            self.calls = []

        async def execute(self, node, request):
            self.calls.append((node, request))
            data = (
                [{"ifname": "to-p2", "flags": ["UP"], "operstate": "UP"}]
                if request["operation"] == "get_interfaces"
                else {"ipv4Unicast": {"peers": {"10.254.0.2": {"state": "Established"}}}}
                if request["protocol"] == "bgp"
                else {"10.254.0.2": [{"nbrState": "Full/-", "ifaceName": "to-p2:10.200.1.2"}]}
            )
            return {
                "status": "ok",
                "data": data,
                "error_code": None,
                "raw_evidence": json.dumps(data),
                "duration_ms": 1,
                "truncated": False,
            }

    c.server.adapter = Adapter()


@then(
    "the inspector response preserves independent interfaces BGP and OSPF observations with times"
)
def inspector_observed(c):
    assert c.response.status == 200, c.response.body
    data = json.loads(c.response.body)
    assert data["node_id"] == "p1" and data["generation"] == c.generation
    assert set(data["data"]) == {"interfaces", "bgp", "ospf"}
    for source in data["data"].values():
        assert (
            source["collected_at"]
            and source["source"] == "node_dispatcher"
            and source["error_code"] is None
        )
    assert data["data"]["interfaces"]["data"][0]["operstate"] == "UP"
    assert (
        data["data"]["bgp"]["data"]["ipv4Unicast"]["peers"]["10.254.0.2"]["state"] == "Established"
    )


@given("interface collection times out")
def inspector_failure(c):
    original = c.server.adapter.execute

    async def execute(node, request):
        if request["operation"] == "get_interfaces":
            return {
                "status": "unavailable",
                "error_code": "execution_timeout",
                "data": None,
                "raw_evidence": "",
                "duration_ms": 1,
                "truncated": False,
            }
        return await original(node, request)

    c.server.adapter.execute = execute


@then("the unavailable interface source is explicit while successful neighbor facts remain visible")
def inspector_partial(c):
    assert c.response.status == 200, c.response.body
    data = json.loads(c.response.body)["data"]
    assert (
        data["interfaces"]["error_code"] == "execution_timeout"
        and data["interfaces"]["data"] is None
    )
    assert data["bgp"]["error_code"] is None


@then("the inspector adapter has executed no requests")
def no_requests(c):
    assert not c.server.adapter.calls
