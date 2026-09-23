/** Create local credentials once; print only the destination, never values. */
import { chmod } from "node:fs/promises";
import { root } from "./topology";
const path = `${root}/secrets/mcp-tokens.json`;
if (await Bun.file(path).exists())
  throw Error("Credentials already exist; refusing overwrite");
await Bun.write(
  path,
  JSON.stringify({
    operator: crypto.randomUUID() + crypto.randomUUID(),
    god: crypto.randomUUID() + crypto.randomUUID(),
  }) + "\n",
);
await chmod(path, 0o600);
console.log(
  "Created secrets/mcp-tokens.json (0600). For container use, grant UID 10001 read access via ACL; never broaden world permissions.",
);
