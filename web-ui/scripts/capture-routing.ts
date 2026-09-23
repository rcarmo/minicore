/** Capture the live local routing view. No credentials are read or exported. */
import { chromium } from "playwright";
const browser = await chromium.launch({
  args: ["--no-sandbox", "--enable-unsafe-swiftshader"],
});
try {
  const page = await browser.newPage({
    viewport: { width: 1600, height: 1100 },
  });
  await page.goto("http://127.0.0.1:19000/#p1");
  await page.getByRole("button", { name: "BGP", exact: true }).click();
  await page
    .getByRole("region", { name: "Routing layers" })
    .getByText("ok · 6/6 collected", { exact: true })
    .waitFor();
  await page.screenshot({
    path: "../docs/evidence/routing-bgp.png",
    fullPage: true,
  });
  await page.getByRole("button", { name: "Prefix", exact: true }).click();
  await page
    .getByRole("region", { name: "Routing layers" })
    .getByText("ok · 6/6 collected", { exact: true })
    .waitFor();
  await page.screenshot({
    path: "../docs/evidence/routing-prefix.png",
    fullPage: true,
  });
} finally {
  await browser.close();
}
