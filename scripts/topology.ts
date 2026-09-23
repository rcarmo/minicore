/** Canonical topology loader and deterministic Compose/config renderer. No Docker API in service. */
import { join } from "node:path";
import { mkdir } from "node:fs/promises";
export const root = join(import.meta.dir, "..");
export interface Node {
  id: string;
  label: string;
  role: string;
  kind: string;
  service: string;
  asn: number | null;
  loopback: string | null;
  management_address: string | null;
  protocols: string[];
  position: { x: number; y: number; z: number };
}
export interface Link {
  id: string;
  network: string;
  subnet: string;
  bridge_gateway: string;
  endpoints: { node: string; interface: string; address: string }[];
}
export interface Topology {
  schema_version: string;
  lab_id: string;
  generation: number;
  management: {
    network: string;
    subnet: string;
    gateway: string;
    service_address: string;
  };
  nodes: Node[];
  links: Link[];
}
export async function loadTopology(): Promise<Topology> {
  const t = (await Bun.file(
    join(root, "inventory/topology.json"),
  ).json()) as Topology;
  const ip = (address: string): number => {
    const parts = address.split(".");
    if (
      parts.length !== 4 ||
      parts.some((p) => !/^\d+$/.test(p) || Number(p) > 255)
    )
      throw Error("Invalid IPv4 address");
    return parts.reduce((total, p) => total * 256 + Number(p), 0);
  };
  const ranges: [number, number][] = [];
  const addSubnet = (cidr: string) => {
    const [address, bits] = cidr.split("/");
    const prefix = Number(bits);
    if (!Number.isInteger(prefix) || prefix < 8 || prefix > 30)
      throw Error("Invalid subnet prefix");
    const start = ip(address),
      size = 2 ** (32 - prefix);
    if (
      start % size !== 0 ||
      ranges.some(([lo, hi]) => start <= hi && start + size - 1 >= lo)
    )
      throw Error("Overlapping or noncanonical subnet");
    ranges.push([start, start + size - 1]);
    return [start, start + size - 1];
  };
  addSubnet(t.management.subnet);
  const ids = new Set<string>(),
    services = new Set<string>(),
    interfaces = new Set<string>(),
    networks = new Set<string>();
  if (
    t.schema_version !== "1.0" ||
    t.nodes.length !== 8 ||
    t.links.length !== 9
  )
    throw Error("Expected schema 1.0, eight nodes and nine links");
  for (const n of t.nodes) {
    if (
      !/^[a-z][a-z0-9]{1,15}$/.test(n.id) ||
      ids.has(n.id) ||
      services.has(n.service) ||
      n.service !== n.id
    )
      throw Error("Invalid or duplicate node/service");
    ids.add(n.id);
    services.add(n.service);
  }
  for (const l of t.links) {
    if (
      networks.has(l.network) ||
      l.endpoints.length !== 2 ||
      l.endpoints[0].node === l.endpoints[1].node
    )
      throw Error("Invalid link");
    networks.add(l.network);
    const [lo, hi] = addSubnet(l.subnet);
    const addresses = new Set([l.bridge_gateway]);
    if (ip(l.bridge_gateway) <= lo || ip(l.bridge_gateway) >= hi)
      throw Error("Invalid bridge gateway");
    for (const e of l.endpoints) {
      const k = e.node + ":" + e.interface;
      if (!ids.has(e.node) || interfaces.has(k) || e.interface.length > 15)
        throw Error("Invalid endpoint");
      const [address, bits] = e.address.split("/");
      if (
        !/^[a-z][a-z0-9-]{1,14}$/.test(e.interface) ||
        bits !== l.subnet.split("/")[1] ||
        ip(address) <= lo ||
        ip(address) >= hi ||
        addresses.has(address)
      )
        throw Error("Invalid endpoint address/interface");
      addresses.add(address);
      interfaces.add(k);
    }
  }
  return t;
}
const routerImage = "minicore-router:10.4.1-plain";
const endpointImage =
  "alpine:3.22.1@sha256:eafc1edb577d2e9b458664a15f23ea1c370214193226069eb22921169fc7e43f";
export function compose(t: Topology) {
  const services: Record<string, unknown> = {};
  const networks: Record<string, unknown> = {};
  networks.ingress = { driver: "bridge" };
  networks.management = {
    internal: true,
    driver: "bridge",
    ipam: {
      config: [{ subnet: t.management.subnet, gateway: t.management.gateway }],
    },
  };
  services.management = {
    build: { context: "..", dockerfile: "mcp-service/Dockerfile" },
    image: "minicore-management:0.1.0",
    init: true,
    user: "10001:10001",
    read_only: true,
    cap_drop: ["ALL"],
    security_opt: ["no-new-privileges:true"],
    pids_limit: 64,
    mem_limit: "256m",
    cpus: 1,
    tmpfs: ["/tmp:size=16m,mode=1777"],
    environment: {
      PYTHONDONTWRITEBYTECODE: "1",
      MINICORE_EXPOSURE_PROFILE: "${MINICORE_EXPOSURE_PROFILE:-private}",
      MINICORE_TOKEN_FILE: "/run/secrets/mcp-tokens.json",
      MINICORE_OBSERVATIONS: "/runtime/observations.json",
      MINICORE_ALLOWED_ORIGINS:
        "${MINICORE_ALLOWED_ORIGINS:-http://127.0.0.1:19000}",
    },
    ports: ["${MINICORE_BIND:-127.0.0.1}:${MINICORE_PORT:-19000}:9000"],
    volumes: [
      "../inventory:/app/inventory:ro",
      "../configs:/app/configs:ro",
      "../runtime:/runtime:ro",
      "../secrets:/run/secrets:ro",
    ],
    networks: {
      ingress: { interface_name: "ingress0", gw_priority: 1 },
      management: {
        ipv4_address: t.management.service_address,
        interface_name: "mgmt0",
      },
    },
    healthcheck: {
      test: [
        "CMD",
        "python",
        "-c",
        "import urllib.request;urllib.request.urlopen('http://127.0.0.1:9000/healthz',timeout=2)",
      ],
      interval: "10s",
      timeout: "3s",
      retries: 3,
      start_period: "5s",
    },
    logging: {
      driver: "json-file",
      options: { "max-size": "5m", "max-file": "3" },
    },
  };
  for (const n of t.nodes) {
    const attached: Record<string, unknown> = {};
    if (n.management_address)
      attached.management = {
        ipv4_address: n.management_address,
        interface_name: "mgmt0",
      };
    for (const l of t.links) {
      const e = l.endpoints.find((e) => e.node === n.id);
      if (e)
        attached[l.network] = {
          ipv4_address: e.address.split("/")[0],
          interface_name: e.interface,
        };
    }
    const endpoint = n.kind === "endpoint";
    const lan = t.links.find((l) => l.endpoints.some((e) => e.node === n.id));
    const gateway = lan?.endpoints
      .find((e) => e.node !== n.id)
      ?.address.split("/")[0];
    services[n.service] = {
      profiles: ["lab"],
      image: endpoint ? endpointImage : routerImage,
      ...(!endpoint
        ? { build: { context: "..", dockerfile: "router-image/Dockerfile" } }
        : {}),
      hostname: n.id,
      labels: { "io.minicore.node": n.id, "io.minicore.lab": t.lab_id },
      cap_drop: ["ALL"],
      cap_add: endpoint
        ? ["NET_ADMIN", "NET_RAW"]
        : [
            "NET_ADMIN",
            "NET_RAW",
            "NET_BIND_SERVICE",
            "SETUID",
            "SETGID",
            "CHOWN",
            "DAC_OVERRIDE",
            "FOWNER",
          ],
      security_opt: ["no-new-privileges:true"],
      sysctls: { "net.ipv4.ip_forward": endpoint ? "0" : "1" },
      networks: attached,
      mem_limit: "192m",
      pids_limit: 64,
      ...(endpoint
        ? {
            command: [
              "sh",
              "-c",
              `ip route replace default via ${gateway}; exec sleep infinity`,
            ],
          }
        : {
            volumes: [
              `../configs/${n.id}/frr.conf:/etc/frr/frr.conf:ro`,
              `../configs/${n.id}/daemons:/etc/frr/daemons:ro`,
            ],
          }),
      healthcheck: {
        test: endpoint
          ? ["CMD-SHELL", "ip route show default | grep -q via"]
          : ["CMD", "/usr/local/bin/node-health"],
        interval: "10s",
        timeout: "3s",
        retries: 6,
      },
      logging: {
        driver: "json-file",
        options: { "max-size": "5m", "max-file": "2" },
      },
    };
  }
  for (const l of t.links)
    networks[l.network] = {
      internal: true,
      driver: "bridge",
      ipam: { config: [{ subnet: l.subnet, gateway: l.bridge_gateway }] },
    };
  return { name: "minicore", services, networks };
}
export function frrConfig(t: Topology, n: Node): string {
  const provider = n.asn === 65000,
    loop = (n.loopback ?? "").split("/")[0];
  const lines = [
    "frr defaults traditional",
    `hostname ${n.id}`,
    "log stdout informational",
    "service integrated-vtysh-config",
    "no ipv6 forwarding",
    "interface lo",
    ` ip address ${n.loopback}`,
  ];
  const adjacent = t.links.filter((l) =>
    l.endpoints.some((e) => e.node === n.id),
  );
  for (const l of adjacent) {
    const own = l.endpoints.find((e) => e.node === n.id)!;
    const peer = t.nodes.find(
      (p) => p.id === l.endpoints.find((e) => e.node !== n.id)!.node,
    )!;
    lines.push(`interface ${own.interface}`);
    if (provider && peer.asn === 65000)
      lines.push(" ip ospf area 0", " ip ospf network point-to-point");
  }
  if (provider)
    lines.push(
      "interface lo",
      " ip ospf area 0",
      "router ospf",
      ` ospf router-id ${loop}`,
      " passive-interface lo",
    );
  const lan1 = t.links.find((l) => l.id === "host1-ce1")!.subnet,
    lan2 = t.links.find((l) => l.id === "host2-ce2")!.subnet;
  lines.push(
    `ip prefix-list CUSTOMER seq 10 permit ${lan1}`,
    `ip prefix-list CUSTOMER seq 20 permit ${lan2}`,
  );
  lines.push(
    `router bgp ${n.asn}`,
    ` bgp router-id ${loop}`,
    " no bgp ebgp-requires-policy",
    " no bgp default ipv4-unicast",
  );
  const neighbours: { ip: string; asn: number; internal: boolean }[] = [];
  if (provider)
    for (const p of t.nodes.filter((p) => p.asn === 65000 && p.id !== n.id)) {
      const ip = p.loopback!.split("/")[0];
      neighbours.push({ ip, asn: 65000, internal: true });
      lines.push(
        ` neighbor ${ip} remote-as ${p.asn}`,
        ` neighbor ${ip} update-source lo`,
      );
    }
  for (const l of adjacent) {
    const e = l.endpoints.find((e) => e.node !== n.id)!;
    const p = t.nodes.find((p) => p.id === e.node)!;
    if (p.asn && p.asn !== n.asn) {
      const ip = e.address.split("/")[0];
      neighbours.push({ ip, asn: p.asn, internal: false });
      lines.push(` neighbor ${ip} remote-as ${p.asn}`);
    }
  }
  lines.push(" address-family ipv4 unicast");
  for (const p of neighbours) {
    lines.push(
      `  neighbor ${p.ip} activate`,
      `  neighbor ${p.ip} prefix-list CUSTOMER in`,
      `  neighbor ${p.ip} prefix-list CUSTOMER out`,
    );
    if (p.internal && n.role === "pe")
      lines.push(`  neighbor ${p.ip} next-hop-self`);
  }
  if (n.role === "ce") lines.push(`  network ${n.id === "ce1" ? lan1 : lan2}`);
  lines.push(" exit-address-family", "!");
  return lines.join("\n") + "\n";
}
if (import.meta.main) {
  const t = await loadTopology();
  const files: Record<string, string> = {
    "compose/compose.json": JSON.stringify(compose(t), null, 2) + "\n",
    "configs/daemons":
      'zebra=yes\nbgpd=yes\nospfd=yes\nvtysh_enable=yes\nzebra_options=" -A 127.0.0.1"\nbgpd_options=" -A 127.0.0.1"\nospfd_options=" -A 127.0.0.1"\n',
  };
  for (const n of t.nodes) {
    if (n.kind === "router") {
      files[`configs/${n.id}/frr.conf`] = frrConfig(t, n);
      files[`configs/${n.id}/daemons`] = files["configs/daemons"];
    } else {
      const link = t.links.find((l) =>
        l.endpoints.some((e) => e.node === n.id),
      )!;
      files[`configs/${n.id}/network.json`] =
        JSON.stringify(
          {
            node_id: n.id,
            interface: link.endpoints.find((e) => e.node === n.id)!.interface,
            address: link.endpoints.find((e) => e.node === n.id)!.address,
            gateway: link.endpoints
              .find((e) => e.node !== n.id)!
              .address.split("/")[0],
            forwarding: false,
          },
          null,
          2,
        ) + "\n";
    }
  }
  for (const [path, text] of Object.entries(files)) {
    const full = join(root, path);
    if (process.argv.includes("--check")) {
      if (
        !(await Bun.file(full).exists()) ||
        (await Bun.file(full).text()) !== text
      )
        throw Error(`Stale generated file: ${path}`);
    } else await Bun.write(full, text);
  }
  await mkdir(join(root, "runtime"), { recursive: true });
  await mkdir(join(root, "secrets"), { recursive: true });
  console.log(
    `Topology validated: ${t.nodes.length} nodes / ${t.links.length} data links`,
  );
}
