import { test, expect } from "bun:test";
import { parseFeature } from "../scripts/feature-inventory";
const body =
  "Feature: Coverage\n  Scenario: Observe\n    When state is read\n    Then state is known\n";

test("coverage gate rejects missing, contradictory or evasive classification", () => {
  for (const tags of [
    "",
    "@implemented",
    "@implemented @python @host",
    "@implemented @planned @python",
  ])
    expect(() =>
      parseFeature("features/test.feature", tags + "\n" + body),
    ).toThrow();
  expect(() =>
    parseFeature(
      "features/planned/test.feature",
      "@implemented @python\n" + body,
    ),
  ).toThrow();
  expect(() =>
    parseFeature("features/test.feature", "@planned\n" + body),
  ).toThrow();
  expect(() =>
    parseFeature(
      "features/test.feature",
      "@implemented @python\n" +
        body.replace("  Scenario:", "  @skip\n  Scenario:"),
    ),
  ).toThrow();
});

test("coverage gate recognizes one runnable scenario and preserved plans", () => {
  const implemented = parseFeature(
    "features/test.feature",
    "@implemented @python\n" + body,
  );
  expect(implemented.scenarios[0].cases).toBe(1);
  expect(implemented.scenarios[0].caseIds[0]).toMatchObject({
    key: "features/test.feature:3",
    playwrightTitle: "Observe",
    behaveSuffix: null,
  });
  expect(
    parseFeature("features/planned/test.feature", "@planned\n" + body).status,
  ).toBe("planned");
});

test("coverage gate preserves outline identity across multiple Examples blocks", () => {
  const feature = parseFeature(
    "features/test.feature",
    [
      "@implemented @host",
      "Feature: Coverage",
      "  Background:",
      "    Given setup",
      "",
      "  Scenario Outline: Distinguish examples",
      '    When item "<value>" is checked',
      "    Then it passes",
      "    Examples:",
      "      | value |",
      "      | one   |",
      "      | two   |",
      "",
      "    Examples:",
      "      | value |",
      "      | three |",
    ].join("\n"),
  );
  expect(feature.scenarios).toHaveLength(1);
  expect(feature.scenarios[0].cases).toBe(3);
  expect(feature.scenarios[0].caseIds).toMatchObject([
    {
      key: "features/test.feature:6@1.1",
      order: 1,
      scenarioLine: 6,
      exampleBlock: 1,
      exampleRow: 1,
      playwrightTitle: "Example #1",
      behaveSuffix: "@1.1",
    },
    {
      key: "features/test.feature:6@1.2",
      order: 2,
      exampleBlock: 1,
      exampleRow: 2,
      playwrightTitle: "Example #2",
      behaveSuffix: "@1.2",
    },
    {
      key: "features/test.feature:6@2.1",
      order: 3,
      exampleBlock: 2,
      exampleRow: 1,
      playwrightTitle: "Example #3",
      behaveSuffix: "@2.1",
    },
  ]);
});
