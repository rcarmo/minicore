import { test, expect } from "bun:test";
import { mkdtemp, cp, mkdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
const root = join(import.meta.dir, "../..");

async function withGateProject(
  files: Record<string, string>,
  reports: { web?: any; python?: any },
) {
  const dir = await mkdtemp(join(tmpdir(), "minicore-report-"));
  try {
    await mkdir(join(dir, "web-ui/scripts"), { recursive: true });
    await mkdir(join(dir, "reports"), { recursive: true });
    for (const file of ["verify-acceptance.ts", "feature-inventory.ts"])
      await cp(
        join(root, "web-ui/scripts", file),
        join(dir, "web-ui/scripts", file),
      );
    await symlink(
      join(root, "web-ui/node_modules"),
      join(dir, "web-ui/node_modules"),
    );
    for (const [path, text] of Object.entries(files)) {
      await mkdir(join(dir, path, ".."), { recursive: true });
      await Bun.write(join(dir, path), text);
    }
    await Bun.write(
      join(dir, "reports/bdd-web.json"),
      JSON.stringify(reports.web ?? { errors: [], suites: [] }),
    );
    await Bun.write(
      join(dir, "reports/bdd-python.json"),
      JSON.stringify(reports.python ?? []),
    );
    const p = Bun.spawn(
      ["bun", join(dir, "web-ui/scripts/verify-acceptance.ts")],
      {
        stdout: "pipe",
        stderr: "pipe",
      },
    );
    const stdout = await new Response(p.stdout).text();
    const stderr = await new Response(p.stderr).text();
    return { code: await p.exited, stdout, stderr };
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
}

test("acceptance gate rejects unexpected passing report entries", async () => {
  const result = await withGateProject(
    {
      "features/operations/example.feature":
        "@implemented @host\nFeature: Gate\n  Scenario Outline: Preserve identity\n    When a value <value> is tested\n    Then it passes\n    Examples:\n      | value |\n      | one |\n      | two |\n\n  Scenario: Stable single case\n    When a stable value is tested\n    Then it passes\n",
      "features/diagnostics/example.feature":
        "@implemented @python\nFeature: Python Gate\n  Scenario Outline: Preserve behave identity\n    When a value <value> is checked\n    Then it passes\n    Examples:\n      | value |\n      | one |\n      | two |\n",
    },
    {
      web: {
        errors: [],
        suites: [
          {
            title: "features/operations/example.feature.spec.js",
            file: "features/operations/example.feature.spec.js",
            specs: [],
            suites: [
              {
                title: "Gate",
                specs: [
                  {
                    title: "Stable single case",
                    file: "features/operations/example.feature.spec.js",
                    ok: true,
                    tests: [
                      { status: "expected", results: [{ status: "passed" }] },
                    ],
                  },
                  {
                    title: "Unknown extra current result",
                    file: "features/operations/example.feature.spec.js",
                    ok: true,
                    tests: [
                      { status: "expected", results: [{ status: "passed" }] },
                    ],
                  },
                ],
                suites: [
                  {
                    title: "Preserve identity",
                    file: "features/operations/example.feature.spec.js",
                    specs: [
                      {
                        title: "Example #1",
                        file: "features/operations/example.feature.spec.js",
                        ok: true,
                        tests: [
                          {
                            status: "expected",
                            results: [{ status: "passed" }],
                          },
                        ],
                      },
                      {
                        title: "Example #2",
                        file: "features/operations/example.feature.spec.js",
                        ok: true,
                        tests: [
                          {
                            status: "expected",
                            results: [{ status: "passed" }],
                          },
                        ],
                      },
                    ],
                    suites: [],
                  },
                ],
              },
            ],
          },
          {
            title: "features/operations/unknown.feature.spec.js",
            file: "features/operations/unknown.feature.spec.js",
            specs: [
              {
                title: "Entire unknown feature result",
                file: "features/operations/unknown.feature.spec.js",
                ok: true,
                tests: [
                  { status: "expected", results: [{ status: "passed" }] },
                ],
              },
            ],
            suites: [],
          },
        ],
      },
      python: [
        {
          location: "features/diagnostics/example.feature:2",
          elements: [
            {
              type: "scenario",
              location: "features/diagnostics/example.feature:8",
              name: "Preserve behave identity -- @1.1 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
            {
              type: "scenario",
              location: "features/diagnostics/example.feature:4",
              name: "Unknown passing scenario",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
            {
              type: "scenario",
              location: "features/diagnostics/example.feature:9",
              name: "Preserve behave identity -- @1.2 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
          ],
        },
        {
          location: "features/diagnostics/unknown.feature:2",
          elements: [
            {
              type: "scenario",
              location: "features/diagnostics/unknown.feature:3",
              name: "Entire unknown feature result",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
          ],
        },
      ],
    },
  );
  expect(result.code).not.toBe(0);
  expect(result.stderr).toContain("Unexpected");
});

test("acceptance gate rejects mismatched outline identity despite equal passing counts", async () => {
  const result = await withGateProject(
    {
      "features/operations/example.feature":
        "@implemented @host\nFeature: Gate\n  Scenario Outline: Preserve identity\n    When a value <value> is tested\n    Then it passes\n    Examples:\n      | value |\n      | one |\n",
    },
    {
      web: {
        errors: [],
        suites: [
          {
            title: "example",
            suites: [
              {
                title: "Gate",
                suites: [
                  {
                    title: "A different untested behavior",
                    specs: [
                      {
                        title: "Example #1",
                        file: "features/operations/example.feature.spec.js",
                        ok: true,
                        tests: [
                          {
                            status: "expected",
                            results: [{ status: "passed" }],
                          },
                        ],
                      },
                    ],
                  },
                ],
                specs: [],
              },
            ],
            specs: [],
          },
        ],
      },
    },
  );
  expect(result.code).not.toBe(0);
  expect(result.stderr).toContain("Missing Playwright mapping");
});

test("acceptance gate rejects duplicate outline examples that masquerade as complete passing coverage", async () => {
  const result = await withGateProject(
    {
      "features/operations/example.feature":
        "@implemented @host\nFeature: Gate\n  Scenario Outline: Preserve identity\n    When a value <value> is tested\n    Then it passes\n    Examples:\n      | value |\n      | one |\n      | two |\n",
      "features/diagnostics/example.feature":
        "@implemented @python\nFeature: Python Gate\n  Scenario Outline: Preserve behave identity\n    When a value <value> is checked\n    Then it passes\n    Examples:\n      | value |\n      | one |\n      | two |\n",
    },
    {
      web: {
        errors: [],
        suites: [
          {
            title: "features/operations/example.feature.spec.js",
            file: "features/operations/example.feature.spec.js",
            specs: [],
            suites: [
              {
                title: "Gate",
                specs: [],
                suites: [
                  {
                    title: "Preserve identity",
                    file: "features/operations/example.feature.spec.js",
                    specs: [
                      {
                        title: "Example #1",
                        file: "features/operations/example.feature.spec.js",
                        ok: true,
                        tests: [
                          {
                            status: "expected",
                            results: [{ status: "passed" }],
                          },
                        ],
                      },
                      {
                        title: "Example #1",
                        file: "features/operations/example.feature.spec.js",
                        ok: true,
                        tests: [
                          {
                            status: "expected",
                            results: [{ status: "passed" }],
                          },
                        ],
                      },
                    ],
                    suites: [],
                  },
                ],
              },
            ],
          },
        ],
      },
      python: [
        {
          location: "features/diagnostics/example.feature:2",
          elements: [
            {
              type: "scenario",
              location: "features/diagnostics/example.feature:8",
              name: "Preserve behave identity -- @1.1 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
            {
              type: "scenario",
              location: "features/diagnostics/example.feature:8",
              name: "Preserve behave identity -- @1.1 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
          ],
        },
      ],
    },
  );
  expect(result.code).not.toBe(0);
  expect(result.stderr).toContain("Duplicate Playwright mapping");
  expect(result.stderr).toContain("Missing Playwright mapping");
  expect(result.stderr).toContain("Duplicate Behave mapping");
  expect(result.stderr).toContain("Missing Behave mapping");
});

test("acceptance gate accepts exact ordinary and expanded case identities", async () => {
  const result = await withGateProject(
    {
      "features/p.feature":
        "@implemented @python\nFeature: Python\n  Scenario Outline: Identity <value>\n    Then check <value>\n    Examples:\n      | value |\n      | one |\n      | two |\n",
      "features/w.feature":
        "@implemented @browser\nFeature: Web\n  Scenario: Page\n    Then page appears\n",
    },
    {
      python: [
        {
          location: "features/p.feature:2",
          elements: [
            {
              type: "scenario",
              location: "features/p.feature:7",
              name: "Identity one -- @1.1 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
            {
              type: "scenario",
              location: "features/p.feature:8",
              name: "Identity two -- @1.2 ",
              status: "passed",
              steps: [{ result: { status: "passed" } }],
            },
          ],
        },
      ],
      web: {
        errors: [],
        suites: [
          {
            title: "Web",
            specs: [
              {
                title: "Page",
                file: "features/w.feature.spec.js",
                ok: true,
                tests: [
                  { status: "expected", results: [{ status: "passed" }] },
                ],
              },
            ],
          },
        ],
      },
    },
  );
  expect(result.code).toBe(0);
});
