/** Require every classified current scenario to have a passing runner result. */
import { inventory, type FeatureRecord } from "./feature-inventory";

type ExpectedCase = {
  key: string;
  path: string;
  featureName: string;
  scenarioName: string;
  scenarioLine: number;
  outline: boolean;
  behaveSuffix: string | null;
  playwrightTitle: string;
};

function expectedCases(feature: FeatureRecord): ExpectedCase[] {
  return feature.scenarios.flatMap((scenario) =>
    scenario.caseIds.map((c) => ({
      key: c.key,
      path: feature.path,
      featureName: feature.name,
      scenarioName: scenario.name,
      scenarioLine: scenario.line,
      outline: c.outline,
      behaveSuffix: c.behaveSuffix,
      playwrightTitle: c.playwrightTitle,
    })),
  );
}

function isPassingScenario(scenario: any) {
  return (
    scenario.status === "passed" &&
    Array.isArray(scenario.steps) &&
    scenario.steps.length > 0 &&
    !scenario.steps.some((s: any) => s.result?.status !== "passed")
  );
}

function specs(suites: any[], parents: string[] = []): any[] {
  return suites.flatMap((suite) => {
    const ancestry = [...parents, suite.title];
    return [
      ...(suite.specs ?? []).map((spec: any) => ({ ...spec, ancestry })),
      ...specs(suite.suites ?? [], ancestry),
    ];
  });
}

function parseBehaveCaseKey(
  feature: FeatureRecord,
  scenario: any,
): string | null {
  const [path, lineText] = String(scenario.location ?? "").split(":");
  if (path !== feature.path) return null;
  const line = Number(lineText);
  if (!Number.isInteger(line)) return null;
  // Behave reports outline rows at their Examples-table line, not the outline.
  for (const record of feature.scenarios) {
    for (const item of record.caseIds) {
      const name = String(scenario.name ?? "");
      const expectedName = item.outline
        ? `${item.scenarioName} -- ${item.behaveSuffix}`
        : record.name;
      // Named Examples blocks follow the suffix with their own title.
      const nameMatches = item.outline
        ? name === expectedName || name.startsWith(expectedName + " ")
        : name === expectedName;
      if (item.line === line && nameMatches) return item.key;
    }
  }
  return null;
}

function parsePlaywrightCaseKey(
  feature: FeatureRecord,
  spec: any,
): string | null {
  if (!String(spec.file ?? "").endsWith(feature.path + ".spec.js")) return null;
  const outline = /^Example #(\d+)$/.test(String(spec.title ?? ""));
  if (spec.ancestry.at(outline ? -2 : -1) !== feature.name) return null;
  const scenarioName = outline ? spec.ancestry.at(-1) : spec.title;
  if (!scenarioName) return null;
  const record = feature.scenarios.find((s) => s.name === scenarioName);
  if (!record) return null;
  const example = /^Example #(\d+)$/.exec(String(spec.title ?? ""));
  if (!example) return record.caseIds.find((c) => !c.outline)?.key ?? null;
  const order = Number(example[1]);
  return record.caseIds.find((c) => c.order === order)?.key ?? null;
}

export async function verifyAcceptance(root: string) {
  const records = await inventory(root);
  const python = await Bun.file(root + "/reports/bdd-python.json").json();
  const web = await Bun.file(root + "/reports/bdd-web.json").json();
  const failures: string[] = [];

  for (const feature of records.filter(
    (f) => f.status === "implemented" && f.runner === "python",
  )) {
    const expected = new Map(expectedCases(feature).map((c) => [c.key, c]));
    const matches = new Map<string, any[]>();
    for (const report of python.filter(
      (r: any) => String(r.location ?? "").split(":")[0] === feature.path,
    ))
      for (const scenario of report.elements.filter(
        (s: any) => s.type === "scenario",
      )) {
        const key = parseBehaveCaseKey(feature, scenario);
        if (!key) {
          failures.push(
            `Unexpected Behave result: ${feature.path}: ${scenario.name}`,
          );
          continue;
        }
        matches.set(key, [...(matches.get(key) ?? []), scenario]);
      }
    for (const [key, exp] of expected) {
      const found = matches.get(key) ?? [];
      if (!found.length)
        failures.push(`Missing Behave mapping: ${exp.scenarioName}`);
      else if (found.length !== 1)
        failures.push(`Duplicate Behave mapping: ${exp.scenarioName}`);
      else if (!isPassingScenario(found[0]))
        failures.push(`Nonpassing Behave scenario: ${found[0].name}`);
    }
  }

  const all = specs(web.suites ?? []);
  for (const feature of records.filter(
    (f) => f.status === "implemented" && ["browser", "host"].includes(f.runner),
  )) {
    const expected = new Map(expectedCases(feature).map((c) => [c.key, c]));
    const matches = new Map<string, any[]>();
    for (const spec of all.filter((s) =>
      String(s.file ?? "").endsWith(feature.path + ".spec.js"),
    )) {
      const key = parsePlaywrightCaseKey(feature, spec);
      if (!key) {
        failures.push(
          `Unexpected Playwright result: ${feature.path}: ${spec.title}`,
        );
        continue;
      }
      matches.set(key, [...(matches.get(key) ?? []), spec]);
    }
    for (const [key, exp] of expected) {
      const found = matches.get(key) ?? [];
      if (!found.length)
        failures.push(`Missing Playwright mapping: ${exp.scenarioName}`);
      else if (found.length !== 1)
        failures.push(`Duplicate Playwright mapping: ${exp.scenarioName}`);
      else {
        const scenario = found[0];
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
          failures.push(`Nonpassing Playwright scenario: ${scenario.title}`);
      }
    }
  }
  const pythonPaths = new Set(
    records
      .filter((f) => f.status === "implemented" && f.runner === "python")
      .map((f) => f.path),
  );
  const webPaths = new Set(
    records
      .filter(
        (f) =>
          f.status === "implemented" && ["browser", "host"].includes(f.runner),
      )
      .map((f) => f.path + ".spec.js"),
  );
  for (const report of python) {
    if (!pythonPaths.has(String(report.location ?? "").split(":")[0]))
      failures.push("Unexpected Behave feature");
  }
  for (const report of all) {
    if (![...webPaths].some((path) => String(report.file ?? "").endsWith(path)))
      failures.push("Unexpected Playwright feature");
  }
  if (web.errors?.length) failures.push("Playwright global errors");
  if (failures.length) throw Error(failures.join("\n"));
  console.log(
    `Acceptance gate: every implemented scenario passed; no skipped, undefined or failed current scenarios. Planned and external specifications are excluded explicitly. Duplicate and unexpected results fail the gate.`,
  );
}

const root = import.meta.dir + "/../..";
await verifyAcceptance(root);
