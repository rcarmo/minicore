# Plain-IP FRR node image

The upstream FRR 10.4.1 image requests SYS_ADMIN during startup even when only plain IPv4 OSPF/BGP is used. Minicore builds the pinned GPL-2.0-or-later FRR source and removes the explicit ZCAP_SYS_ADMIN item from the four required daemon capability lists. This is a source change, not `--privileged`, disabling libcap or bypassing kernel checks. It is not suitable for network-namespace/VRF administration.

`make router-build` builds Linux amd64 `minicore-router:10.4.1-plain`. Source tag frr-10.4.1, archive SHA-256 `8e4003eaba168626c5ea7a6735f2c85c87b04214e6f8c8f2715b21f8ae40970b`; upstream image digest is in Dockerfile. Both source and image are publicly obtainable. Build and runtime packages are pinned in `locks/router-build-apk.lock` and `locks/router-runtime-apk.lock`. Downloads still require upstream artifact availability.

Required Docker capabilities: NET_ADMIN, NET_RAW, NET_BIND_SERVICE, SETUID, SETGID, CHOWN, DAC_OVERRIDE, FOWNER, SYS_CHROOT (OpenSSH privilege separation). All others are dropped; no-new-privileges remains. Health requires responsive VTY sockets from zebra, bgpd and ospfd, not merely watchfrr. Each router receives only its own read-only frr.conf and daemons files.

Upstream source and licence: [FRR 10.4.1](https://github.com/FRRouting/frr/tree/frr-10.4.1) and its `COPYING` file. `Dockerfile` records the full source patch. Preserve source and licence obligations when redistributing the image.

Diagnostic and fault SSH use separate forced-command identities. Both are restricted to inventoried operations; neither provides a general shell. See the [node adapter](../docs/specs/live-node-adapter.md) and [fault controller](../docs/specs/fault-controller.md).
