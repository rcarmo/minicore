/** Explicit local key provisioning. Separate identities; never print private material. */
import { chmod, mkdir } from "node:fs/promises";
import { join } from "node:path";
import { loadTopology, root } from "./topology";
const t = await loadTopology();
const base = join(root, "secrets/ssh");
await mkdir(base, { recursive: true });
async function key(path: string) {
  if (await Bun.file(path).exists()) return;
  const p = Bun.spawn(
    ["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", path],
    { stdout: "ignore", stderr: "inherit" },
  );
  if (await p.exited) throw Error("Key generation failed");
}
await key(join(base, "diagnostic"));
await key(join(base, "fault"));
const pub = (await Bun.file(join(base, "diagnostic.pub")).text()).trim();
let known = "";
for (const node of t.nodes.filter((n) => n.kind === "router")) {
  const dir = join(base, node.id);
  await mkdir(dir, { recursive: true });
  const hostPrivate = join(dir, "ssh_host_ed25519_key");
  const exists = Bun.spawn(["sudo", "test", "-f", hostPrivate], {
    stdout: "ignore",
    stderr: "ignore",
  });
  if ((await exists.exited) !== 0) await key(hostPrivate);
  const authWrite = Bun.spawn(["sudo", "tee", join(dir, "authorized_keys")], {
    stdin: "pipe",
    stdout: "ignore",
    stderr: "inherit",
  });
  authWrite.stdin.write(`restrict ${pub}\n`);
  authWrite.stdin.end();
  if (await authWrite.exited) throw Error("Authorized key write failed");
  const permissions = Bun.spawn(["sudo", "chmod", "755", dir], {
    stderr: "inherit",
  });
  if (await permissions.exited) throw Error("Key directory permissions failed");
  const authMode = Bun.spawn(
    ["sudo", "chmod", "644", join(dir, "authorized_keys")],
    { stderr: "inherit" },
  );
  if (await authMode.exited) throw Error("Authorized key permissions failed");
  const host = (await Bun.file(join(dir, "ssh_host_ed25519_key.pub")).text())
    .trim()
    .split(" ")
    .slice(0, 2)
    .join(" ");
  known += `${node.management_address} ${host}\n`;
  // sshd checks root ownership. sudo is local provisioning, never in management.
  const p = Bun.spawn(["sudo", "chown", "-R", "root:root", dir], {
    stderr: "inherit",
  });
  if (await p.exited) throw Error("Node key ownership failed");
  const mode = Bun.spawn(
    ["sudo", "chmod", "600", join(dir, "ssh_host_ed25519_key")],
    { stderr: "inherit" },
  );
  if (await mode.exited) throw Error("Node key permissions failed");
}
const client = join(base, "client");
await mkdir(client, { recursive: true });
const copy = Bun.spawn(
  [
    "sudo",
    "install",
    "-o",
    "10001",
    "-g",
    "10001",
    "-m",
    "600",
    join(base, "diagnostic"),
    join(client, "diagnostic"),
  ],
  { stderr: "inherit" },
);
if (await copy.exited) throw Error("Client identity installation failed");
const knownWrite = Bun.spawn(["sudo", "tee", join(client, "known_hosts")], {
  stdin: "pipe",
  stdout: "ignore",
  stderr: "inherit",
});
knownWrite.stdin.write(known);
knownWrite.stdin.end();
if (await knownWrite.exited) throw Error("Known hosts installation failed");
const mode = Bun.spawn(["sudo", "chmod", "644", join(client, "known_hosts")], {
  stderr: "inherit",
});
if (await mode.exited) throw Error("Known hosts permissions failed");
await chmod(join(base, "fault"), 0o600);
console.log(
  "Provisioned pinned node host keys and diagnostic client identity; separate fault identity is NOT authorised or mounted yet.",
);
