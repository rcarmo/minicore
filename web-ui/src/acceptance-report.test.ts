import { test, expect } from "bun:test";
import { mkdtemp, cp, mkdir, rm, symlink } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
const root = join(import.meta.dir, "../..");
test("acceptance gate rejects mismatched outline identity despite equal passing counts", async () => {
  const dir = await mkdtemp(join(tmpdir(), "minicore-report-"));
  try {
    await mkdir(join(dir, "web-ui/scripts"), { recursive: true });
    await mkdir(join(dir, "reports"));
    for (const file of ["verify-acceptance.ts", "feature-inventory.ts"])
      await cp(
        join(root, "web-ui/scripts", file),
        join(dir, "web-ui/scripts", file),
      );
    await symlink(
      join(root, "web-ui/node_modules"),
      join(dir, "web-ui/node_modules"),
    );
    await mkdir(join(dir, "features/operations"), { recursive: true });
    await Bun.write(
      join(dir, "features/operations/example.feature"),
      "@implemented @host\nFeature: Gate\n  Scenario Outline: Preserve identity\n    When a value <value> is tested\n    Then it passes\n    Examples:\n      | value |\n      | one |\n",
    );
    const report = {
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
                        { status: "expected", results: [{ status: "passed" }] },
                      ],
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };
    await Bun.write(join(dir, "reports/bdd-web.json"), JSON.stringify(report));
    await Bun.write(join(dir, "reports/bdd-python.json"), "[]");
    const p = Bun.spawn(
      ["bun", join(dir, "web-ui/scripts/verify-acceptance.ts")],
      { stdout: "pipe", stderr: "pipe" },
    );
    const text = await new Response(p.stderr).text();
    await new Response(p.stdout).text();
    expect(await p.exited).not.toBe(0);
    expect(text).toContain("Missing Playwright mapping");
  } finally {
    await rm(dir, { recursive: true, force: true });
  }
});
