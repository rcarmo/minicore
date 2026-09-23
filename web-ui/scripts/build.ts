import { mkdir, rm } from "node:fs/promises";
import { join } from "node:path";

const root = import.meta.dir + "/..";
const outdir = join(root, "dist");
await rm(outdir, { recursive: true, force: true });
await mkdir(outdir, { recursive: true });

const result = await Bun.build({
  entrypoints: [join(root, "src/main.tsx"), join(root, "src/styles.css")],
  outdir,
  target: "browser",
  format: "esm",
  minify: true,
  sourcemap: "external",
  naming: "[name].[ext]",
});
if (!result.success) {
  for (const log of result.logs) console.error(log);
  process.exit(1);
}
await Bun.write(
  join(outdir, "index.html"),
  `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><meta name="color-scheme" content="dark light"><title>Minicore Network Lab</title><link rel="stylesheet" href="/assets/styles.css"></head><body><div id="app"><p>Loading Minicore…</p></div><noscript>Minicore requires JavaScript. The structured topology remains available at /api/v1/topology.</noscript><script type="module" src="/assets/main.js"></script></body></html>`,
);

for (const name of ["preact", "three"]) {
  await Bun.write(
    join(outdir, `LICENSE-${name}.txt`),
    await Bun.file(join(root, "node_modules", name, "LICENSE")).text(),
  );
}
