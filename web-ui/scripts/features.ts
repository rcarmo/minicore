/** Classification/syntax/traceability gate, not an assertion of execution. */
import { inventory } from "./feature-inventory";
const root = import.meta.dir + "/../..";
const records = await inventory(root);
const lines = [
  "# Behavioral coverage map",
  "",
  "Generated from `.feature` files by `make coverage-update`. Do not edit by hand.",
  "",
  "Implemented scenarios execute via `make acceptance`: Behave for Python contracts and real transport; Playwright-BDD for browser interactions and host-tool contracts. Host-tool tests substitute a recording Docker executable, never a healthy network. Browser tests use a disposable loopback service, not persisted lab state.",
  "",
  "`external` scenarios need real lab containers and an explicit collector; `planned` scenarios preserve unbound design requirements, including some behaviour covered by narrower implemented scenarios. Neither is counted as passing acceptance. Unit tests complement these scenarios; scenario counts are not line/branch coverage.",
  "",
  "| Feature | Status | Runner | Expanded cases |",
  "|---|---|---|---|",
];
for (const f of records)
  lines.push(
    `| [${f.name}](../../${f.path}) | ${f.status} | ${f.runner} | ${f.scenarios.reduce((n, s) => n + s.cases, 0)} |`,
  );
for (const f of records.filter((f) => f.status === "implemented")) {
  lines.push(
    "",
    `## ${f.name}`,
    `Source: [${f.path}](../../${f.path}) · runner: ${f.runner}`,
    "",
  );
  for (const s of f.scenarios)
    lines.push(
      `- L${s.line}: ${s.name} (${s.cases} case${s.cases === 1 ? "" : "s"})`,
    );
}
const text = lines.join("\n") + "\n",
  path = root + "/docs/development/behavior-coverage.md";
if (process.argv.includes("--write")) await Bun.write(path, text);
else if (
  !(await Bun.file(path).exists()) ||
  (await Bun.file(path).text()) !== text
)
  throw Error("Coverage map is stale; run make coverage-update");
for (const status of ["implemented", "planned", "external"]) {
  const set = records.filter((f) => f.status === status);
  console.log(
    `${status}: ${set.length} features / ${set.reduce((n, f) => n + f.scenarios.reduce((n, s) => n + s.cases, 0), 0)} expanded cases`,
  );
}
