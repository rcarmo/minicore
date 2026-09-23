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
  expect(
    parseFeature("features/test.feature", "@implemented @python\n" + body)
      .scenarios[0].cases,
  ).toBe(1);
  expect(
    parseFeature("features/planned/test.feature", "@planned\n" + body).status,
  ).toBe("planned");
});
