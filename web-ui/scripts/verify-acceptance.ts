/** Require every classified current scenario to have a fresh, passing runner result. */
import { inventory } from "./feature-inventory";
const root = import.meta.dir + "/../..",
  records = await inventory(root);
const python = await Bun.file(root + "/reports/bdd-python.json").json();
const web = await Bun.file(root + "/reports/bdd-web.json").json();
const failures: string[] = [];
for (const feature of records.filter(
  (f) => f.status === "implemented" && f.runner === "python",
)) {
  const report = python.find(
    (r: any) => r.location.split(":")[0] === feature.path,
  );
  if (!report) {
    failures.push("No Behave result: " + feature.path);
    continue;
  }
  const scenarios = report.elements.filter((s: any) => s.type === "scenario");
  const expected = feature.scenarios.reduce((n, s) => n + s.cases, 0);
  if (scenarios.length !== expected)
    failures.push("Behave count mismatch: " + feature.path);
  for (const scenario of scenarios) {
    if (
      scenario.status !== "passed" ||
      scenario.steps.some((s: any) => s.result?.status !== "passed")
    )
      failures.push("Nonpassing Behave scenario: " + scenario.name);
  }
  for (const s of feature.scenarios)
    if (
      scenarios.filter(
        (r: any) => r.name === s.name || r.name.startsWith(s.name + " -- @"),
      ).length !== s.cases
    )
      failures.push("Missing Behave mapping: " + s.name);
}
function specs(suites: any[]): any[] {
  return suites.flatMap((s) => [...(s.specs ?? []), ...specs(s.suites ?? [])]);
}
const all = specs(web.suites);
for (const feature of records.filter(
  (f) => f.status === "implemented" && ["browser", "host"].includes(f.runner),
)) {
  const suite = all.filter((s) => s.file.endsWith(feature.path + ".spec.js"));
  if (suite.length !== feature.scenarios.reduce((n, s) => n + s.cases, 0))
    failures.push("Playwright count mismatch: " + feature.path);
  for (const scenario of suite) {
    if (
      !scenario.ok ||
      scenario.tests.length !== 1 ||
      scenario.tests.some(
        (t: any) =>
          t.status !== "expected" ||
          !t.results.length ||
          t.results.some((r: any) => r.status !== "passed"),
      )
    )
      failures.push("Nonpassing Playwright scenario: " + scenario.title);
  }
  for (const s of feature.scenarios)
    if (
      suite.filter(
        (r) =>
          r.title === s.name ||
          r.title.startsWith(
            "Example #",
          ) /* outlines have parent suite titles checked by generation */,
      ).length < s.cases
    )
      failures.push("Missing Playwright mapping: " + s.name);
}
if (web.errors?.length) failures.push("Playwright global errors");
if (failures.length) throw Error(failures.join("\n"));
console.log(
  `Acceptance gate: every implemented scenario passed; no skipped, undefined or failed current scenarios. Planned and external specifications are excluded explicitly.`,
);
