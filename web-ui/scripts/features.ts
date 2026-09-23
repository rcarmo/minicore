/** Parse every behavioral feature and report executable pickle count; not a behavior runner. */
import {
  Parser,
  AstBuilder,
  GherkinClassicTokenMatcher,
  compile,
} from "@cucumber/gherkin";
import { IdGenerator } from "@cucumber/messages";
const root = import.meta.dir + "/../..";
let scenarios = 0,
  files = 0;
for await (const file of new Bun.Glob("features/**/*.feature").scan({
  cwd: root,
})) {
  const text = await Bun.file(root + "/" + file).text();
  const ids = IdGenerator.incrementing();
  const doc = new Parser(
    new AstBuilder(ids),
    new GherkinClassicTokenMatcher(),
  ).parse(text);
  if (!doc.feature) throw Error(`Missing feature: ${file}`);
  const pickles = compile(doc, file, ids);
  if (!pickles.length) throw Error(`No scenarios: ${file}`);
  scenarios += pickles.length;
  files++;
}
console.log(
  `Gherkin syntax: ${files} features, ${scenarios} expanded scenarios (not execution claims)`,
);
