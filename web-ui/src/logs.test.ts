import { test, expect } from "bun:test";
import { validateLogPage } from "./logs";
const base = {
  node_id: "p1",
  generation: 1,
  status: "ok",
  data: { entries: [], next_cursor: null, revision: "r1" },
};
test("validates node boundary and rows", () => {
  expect(validateLogPage(base, "p1").generation).toBe(1);
  expect(() => validateLogPage(base, "p2")).toThrow();
  expect(() =>
    validateLogPage(
      { ...base, data: { ...base.data, entries: [{ message: "bad" }] } },
      "p1",
    ),
  ).toThrow();
  expect(() =>
    validateLogPage(
      { ...base, data: { ...base.data, entries: Array(501).fill({}) } },
      "p1",
    ),
  ).toThrow();
});
