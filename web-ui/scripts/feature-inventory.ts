import {
  Parser,
  AstBuilder,
  GherkinClassicTokenMatcher,
  compile,
} from "@cucumber/gherkin";
import { IdGenerator } from "@cucumber/messages";
export type FeatureRecord = {
  path: string;
  name: string;
  status: string;
  runner: string;
  scenarios: { name: string; line: number; cases: number }[];
};
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
  return {
    path,
    name: doc.feature.name,
    status: lifecycle[0].slice(1),
    runner:
      runners[0]?.slice(1) ??
      (lifecycle[0] === "@external" ? "live lab" : "not bound"),
    scenarios: scenarios.map((s) => ({
      name: s.name,
      line: s.location.line,
      cases: pickles.filter((p) => p.astNodeIds.includes(s.id)).length,
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
