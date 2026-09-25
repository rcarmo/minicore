# Routing domains, prefix visibility and observed faults

The workbench exposes routing-layer views for the fixed simulator in [../../SPEC.md](../../SPEC.md).

## Current scope

The browser provides:

- AS and OSPF area grouping derived from inventory.
- BGP and OSPF relationship displays from bounded routing evidence.
- Prefix selection from inventoried endpoint-LAN prefixes.
- God and Agent evidence projection in the browser.
- Measured state changes during fault exercises.

## Evidence rules

Routing presentation keeps these facts separate:

- physical links versus logical peerings;
- BGP, router RIB and kernel forwarding evidence;
- declared baseline versus measured runtime state;
- observed withdrawal versus failed or stale collection;
- Operator evidence projection versus God controller ground truth.

## Domain and prefix model

AS 65000 contains `p1`, `p2`, `pe1` and `pe2`. `ce1` is AS 65001. `ce2` is AS 65002. `host1` and `host2` are packet endpoints on endpoint LANs and are not BGP speakers.

The exact selectable prefixes are `10.200.8.0/29` and `10.200.9.0/29`. Prefix evidence is bounded to inventoried choices and bounded router reads. A covering aggregate or default route does not count as visibility of the selected exact prefix.

## Fault presentation

Ordinary browser evidence can show interface state changes, OSPF or BGP changes, prefix disappearance from successful collections, probe loss and latency, and explicit collection failure. God view can additionally show scenario and controller state. Toggling view changes projection only. It does not change capability or mutate the lab.
