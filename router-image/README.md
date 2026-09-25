# Plain-IP FRR node image

Minicore builds FRR 10.4.1 for IPv4 OSPF/BGP without `SYS_ADMIN`. The source patch removes `ZCAP_SYS_ADMIN` from four daemon capability lists. Kernel capability checks remain active. Network-namespace and VRF administration that require this capability are unsupported.

Run `make router-build` from the repository root to build Linux amd64 image `minicore-router:10.4.1-plain`.

## Source and packages

- Source tag: `frr-10.4.1`.
- Archive SHA-256: `8e4003eaba168626c5ea7a6735f2c85c87b04214e6f8c8f2715b21f8ae40970b`.
- Base-image digest and full source patch: [Dockerfile](Dockerfile).
- Package versions: [build lock](../locks/router-build-apk.lock) and [runtime lock](../locks/router-runtime-apk.lock).

Downloads require upstream artifact availability. FRR is GPL-2.0-or-later; see [upstream source and COPYING](https://github.com/FRRouting/frr/tree/frr-10.4.1). Preserve source and licence obligations when redistributing the image.

## Runtime permissions

The image requires `NET_ADMIN`, `NET_RAW`, `NET_BIND_SERVICE`, `SETUID`, `SETGID`, `CHOWN`, `DAC_OVERRIDE`, `FOWNER` and `SYS_CHROOT`. OpenSSH uses `SYS_CHROOT` for privilege separation. All other capabilities are dropped and `no-new-privileges` is enabled.

Health checks require responsive VTY sockets from `zebra`, `bgpd` and `ospfd`. Each router receives only its own read-only `frr.conf` and `daemons` files.

Diagnostic and fault SSH use separate forced-command identities restricted to inventoried operations. Neither provides a general shell. See the [node adapter](../docs/specs/live-node-adapter.md) and [fault controller](../docs/specs/fault-controller.md).
