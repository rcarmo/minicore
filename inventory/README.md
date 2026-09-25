# Topology inventory

Edit [topology.json](topology.json), then run `make generate` from the repository root. Nodes map to Compose services; links map to bridge networks with fixed interface names and addresses. The browser combines a filtered inventory projection with timestamped observations.

Keep fault-controller state and credentials out of the inventory. See [SPEC.md](../SPEC.md) for addressing and routing requirements.
