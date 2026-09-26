import {
  Parser,
  AstBuilder,
  GherkinClassicTokenMatcher,
  compile,
} from "@cucumber/gherkin";
import { IdGenerator } from "@cucumber/messages";

type ScenarioCase = {
  key: string;
  line: number;
  order: number;
  outline: boolean;
  scenarioLine: number;
  scenarioName: string;
  behaveSuffix: string | null;
  playwrightTitle: string;
  exampleBlock: number | null;
  exampleRow: number | null;
  exampleLine: number | null;
};

type ScenarioRecord = {
  name: string;
  line: number;
  cases: number;
  caseIds: ScenarioCase[];
};

export type FeatureRecord = {
  path: string;
  name: string;
  status: string;
  runner: string;
  scenarios: ScenarioRecord[];
};

function buildScenarioCases(path: string, scenario: any): ScenarioCase[] {
  if (scenario.keyword !== "Scenario Outline")
    return [
      {
        key: `${path}:${scenario.location.line}`,
        line: scenario.location.line,
        order: 1,
        outline: false,
        scenarioLine: scenario.location.line,
        scenarioName: scenario.name,
        behaveSuffix: null,
        playwrightTitle: scenario.name,
        exampleBlock: null,
        exampleRow: null,
        exampleLine: null,
      },
    ];

  const cases: ScenarioCase[] = [];
  let order = 0;
  for (const [blockIndex, examples] of (scenario.examples ?? []).entries()) {
    for (const [rowIndex, row] of (examples.tableBody ?? []).entries()) {
      order += 1;
      cases.push({
        key: `${path}:${scenario.location.line}@${blockIndex + 1}.${rowIndex + 1}`,
        line: row.location.line,
        order,
        outline: true,
        scenarioLine: scenario.location.line,
        scenarioName: (examples.tableHeader?.cells ?? []).reduce(
          (name: string, cell: any, i: number) =>
            name.split(`<${cell.value}>`).join(row.cells[i].value),
          scenario.name,
        ),
        behaveSuffix: `@${blockIndex + 1}.${rowIndex + 1}`,
        playwrightTitle: `Example #${order}`,
        exampleBlock: blockIndex + 1,
        exampleRow: rowIndex + 1,
        exampleLine: row.location.line,
      });
    }
  }
  return cases;
}

export function parseFeature(path: string, text: string): FeatureRecord {
  const ids = IdGenerator.incrementing(),
    doc = new Parser(
      new AstBuilder(ids),
      new GherkinClassicTokenMatcher(),
    ).parse(text);
  if (!doc.feature) throw Error(`Missing feature: ${path}`);
  const tags = doc.feature.tags.map((t) => t.name);
  const lifecycle = tags.filter((t) =>
    ["@implemented", "@planned", "@external"].includes(t),
  );
  if (lifecycle.length !== 1)
    throw Error(`Exactly one lifecycle tag required: ${path}`);
  const runners = tags.filter((t) =>
    ["@python", "@browser", "@host"].includes(t),
  );
  if (lifecycle[0] === "@implemented" && runners.length !== 1)
    throw Error(`Exactly one runner required: ${path}`);
  if (lifecycle[0] === "@planned" && !path.includes("/planned/"))
    throw Error(`Planned feature must be isolated: ${path}`);
  if (path.includes("/planned/") && lifecycle[0] !== "@planned")
    throw Error(`Planned path cannot be implemented: ${path}`);
  const scenarios = doc.feature.children
    .map((x) => x.scenario)
    .filter((x) => x !== undefined);
  if (!scenarios.length || doc.feature.children.some((x) => x.rule))
    throw Error(`Use nonempty flat features: ${path}`);
  const pickles = compile(doc, path, ids);
  if (new Set(scenarios.map((s) => s.name)).size !== scenarios.length)
    throw Error(`Duplicate scenario name: ${path}`);
  for (const s of scenarios)
    if (
      s.tags.some((t) =>
        [
          "@implemented",
          "@planned",
          "@external",
          "@python",
          "@browser",
          "@host",
          "@skip",
        ].includes(t.name),
      )
    )
      throw Error(
        `Scenario cannot override lifecycle/runner or skip: ${path}:${s.location.line}`,
      );

  const scenarioRecords = scenarios.map((s) => ({
    name: s.name,
    line: s.location.line,
    caseIds: buildScenarioCases(path, s),
  }));
  for (const [index, scenario] of scenarioRecords.entries()) {
    const compiledCases = pickles.filter((p) =>
      p.astNodeIds.includes(scenarios[index].id),
    ).length;
    if (compiledCases !== scenario.caseIds.length)
      throw Error(`Expanded case mismatch: ${path}:${scenario.line}`);
  }
  return {
    path,
    name: doc.feature.name,
    status: lifecycle[0].slice(1),
    runner:
      runners[0]?.slice(1) ??
      (lifecycle[0] === "@external" ? "live lab" : "not bound"),
    scenarios: scenarioRecords.map((s) => ({
      ...s,
      cases: s.caseIds.length,
    })),
  };
}
export async function inventory(root: string) {
  const records: FeatureRecord[] = [];
  for await (const path of new Bun.Glob("features/**/*.feature").scan({
    cwd: root,
  }))
    records.push(parseFeature(path, await Bun.file(root + "/" + path).text()));
  return records.sort((a, b) => a.path.localeCompare(b.path));
}
