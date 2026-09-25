# Dependency and licence inventory

| Component | Pinned source/version | Licence / use |
|---|---|---|
| uMCP | 30cce7dfe08c6ee63de235f7d81754ba286dafbb, metadata 0.2.2 | MIT; vendored source, retained LICENSE; local transport changes documented |
| Python runtime image | 3.12.11-alpine3.22, amd64 sha256:5e511b0e940def74dd23389510300c76017ca9bbc92484c40cff0951adf32245 | PSF and Alpine package licences; upstream runtime image |
| FRR router image | quay.io/frrouting/frr:10.4.1, amd64 sha256:f1dd8182ca8ebd76421378702b95d1553fd7285d63db170640eefeb6f989c9dd | GPL-2.0-or-later FRR and upstream image packages; base for locally rebuilt plain-IP FRR; no SYS_ADMIN grant |
| Endpoint image | alpine:3.22.1, amd64 sha256:eafc1edb577d2e9b458664a15f23ea1c370214193226069eb22921169fc7e43f | Alpine packages under individual OSS licences; includes GPL BusyBox |
| Preact | 10.27.1 | MIT; build-time dependency, bundled runtime code and licence in image |
| Three.js | 0.180.0 | MIT; build-time dependency, bundled runtime code and licence in image |
| TypeScript | 5.9.2 | Apache-2.0; development only |
| Playwright | 1.55.1 | Apache-2.0; development only |
| playwright-bdd | 8.4.1 | MIT; development only |
| Cucumber Gherkin/messages | 35.1.0 / 28.1.0 | MIT; syntax and BDD testing only |
| Prettier | 3.6.2 | MIT; development only |
| Behave | 1.3.3 | BSD-2-Clause; Python Gherkin runner, development only |
| Ruff / mypy | 0.13.1 / 1.18.2 | MIT / MIT; development only |
| Bun | tested 1.4.1 | MIT runtime and tooling; build and test only, not in image |

Exact Bun top-level versions and resolved transitive integrity are in `web-ui/package.json` and `bun.lock`. Python development tool versions are in `requirements-dev.txt`. No external Python runtime dependency is installed. Local package installation is not a security audit of all transitive tooling.

Upstream licences remain with redistributed code. This inventory is not a legal review or vulnerability scan.

The local FRR source variant uses archive SHA-256 `8e4003eaba168626c5ea7a6735f2c85c87b04214e6f8c8f2715b21f8ae40970b` and the full declaration-only patch in `router-image/Dockerfile`. Build and runtime packages are pinned in `locks/`. Source-built binaries supersede the base image APK metadata, so the APK list alone is not a complete SBOM.

Independent test client: official Python `mcp==1.27.2` (MIT), development-only in `requirements-dev.txt`. Its dependencies do not enter the management runtime image. Supported negotiated protocol versions remain `2025-03-26` and `2024-11-05`.

## Release dependency locks

`locks/router-build-apk.lock`, `locks/router-runtime-apk.lock`, and `locks/management-apk.lock` pin every added or updated APK relative to the digest-pinned base. Docker builds use those exact versions and fail if they are unavailable. They do not silently upgrade. `requirements-dev.lock` records the full Python development dependency resolution. `make bootstrap` uses it with Bun's frozen lockfile. Runtime management still has no pip dependencies.

Locks provide version and source reproducibility. They do not provide offline artifacts or bit-identical builds. Package repositories must still retain the pinned artifacts. APK repository signatures authenticate downloads, and FRR source is SHA-256 checked. If an upstream artifact is unavailable, mirror or requalify it deliberately. Do not bypass the locks with floating versions.
