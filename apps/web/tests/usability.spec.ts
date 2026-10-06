import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

// Use only a disposable cached server; no provider/model worker is needed.
const tokenFile = process.env.SCANNER_TEST_TOKEN_FILE;
const fixtureFile = process.env.SCANNER_TEST_REPORT_FIXTURE;
test.beforeEach(async ({ page }) => {
  if (!tokenFile) throw new Error("Set a disposable private server token file");
  await page.goto("/");
  await page
    .getByLabel("Owner token")
    .fill(readFileSync(tokenFile, "utf8").trim());
  await page.getByRole("button", { name: "Connect to private server" }).click();
  await expect(
    page.getByRole("heading", { name: "Home", exact: true }),
  ).toBeVisible();
});

test(
  "company research cannot silently coexist with offline mode",
  { tag: "@usability" },
  async ({ page }) => {
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route(
      (url) => url.pathname === "/api/v1/reports",
      async (route) => {
        await gate;
        await route.continue();
      },
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Home", exact: true }),
    ).toBeVisible();
    const drawer = page.locator(".scan-drawer");
    if (!(await drawer.evaluate((el) => (el as HTMLDetailsElement).open)))
      await drawer.locator("summary").click();
    const offline = page.getByRole("checkbox", {
      name: "Offline: require existing dated cache",
    });
    const research = page.getByLabel("Company research", { exact: true });
    await expect(offline).toBeChecked();
    release();
    await expect(
      page
        .locator(".metric")
        .filter({ hasText: "Latest daily report" })
        .locator("strong"),
    ).not.toHaveText("Not served yet");
    await expect(drawer).toHaveAttribute("open", "");
    await research.selectOption("current");
    await expect(offline).not.toBeChecked();
    await page
      .getByLabel("Mode", { exact: true })
      .selectOption("historical_snapshot");
    await expect(research).toHaveValue("as_of_only");
    await offline.check();
    await expect(research).toHaveValue("none");
    await page.getByLabel("Mode", { exact: true }).selectOption("live");
    await research.selectOption("current");
    const plan = page.waitForResponse((r) =>
      r.url().endsWith("/api/v1/scan-plans"),
    );
    await page.getByRole("button", { name: "Preview date coverage" }).click();
    expect((await plan).request().postDataJSON()).toMatchObject({
      offline: false,
      research: "current",
    });
    await expect(
      page.getByRole("button", { name: "Queue scan", exact: true }),
    ).toBeEnabled();
  },
);

test(
  "usable default, report switching and blocked diagnostics remain distinct",
  { tag: "@usability" },
  async ({ page }) => {
    test.skip(
      !fixtureFile,
      "Needs a disposable latest-blocked/usable report fixture",
    );
    const fixture = JSON.parse(readFileSync(fixtureFile!, "utf8"));
    await page.getByRole("button", { name: "Research", exact: true }).click();
    const report = page.getByLabel("Daily report", { exact: true });
    await expect(report).toHaveValue(fixture.usable);
    await expect(
      page.getByRole("button", { name: "Inspect the blocked scan" }),
    ).toBeVisible();
    await expect(
      page
        .getByText("Company research was not run in this scan.", {
          exact: false,
        })
        .first(),
    ).toBeVisible();
    await expect(page.locator(".stock-title h3")).toBeVisible();
    let release = () => {};
    const gate = new Promise<void>((resolve) => {
      release = resolve;
    });
    await page.route("**/api/v1/market/movement-snapshots", async (route) => {
      if (route.request().postDataJSON().report_id === fixture.other)
        await gate;
      await route.continue();
    });
    try {
      await report.selectOption(fixture.other);
      await expect(page.locator(".stock-title")).toHaveCount(0);
    } finally {
      release();
    }
    await expect(page.locator(".stock-title h3")).toBeVisible();
    await page
      .getByRole("button", { name: "Inspect the blocked scan" })
      .click();
    await expect(report).toHaveValue(fixture.blocked);
    await expect(
      page.getByRole("table").filter({
        has: page.getByText(
          "The read operation timed out; no automatic retry",
          { exact: true },
        ),
      }),
    ).toBeVisible();
    await expect(page.locator(".context-line")).not.toContainText("Ready");
    await expect(page.locator(".stock-title")).toHaveCount(0);
    await page.getByRole("button", { name: "Activity", exact: true }).click();
    await expect(
      page.locator(".job-row").filter({ hasText: "Provider timeout" }),
    ).toBeVisible();
    await expect(
      page.getByText("The exact issue is below.", { exact: false }),
    ).toBeVisible();
    await expect(
      page.locator("details").filter({
        has: page.locator("summary").filter({ hasText: "Job details" }),
      }),
    ).toHaveAttribute("open", "");
  },
);

test(
  "research action prepares an online scan and empty portfolio has a clear start",
  { tag: "@usability" },
  async ({ page }) => {
    test.skip(
      !fixtureFile,
      "Needs a disposable report without company research",
    );
    await page.getByRole("button", { name: "Research", exact: true }).click();
    await page
      .getByRole("link", { name: "Prepare a scan with research" })
      .click();
    await expect(
      page.getByLabel("Company research", { exact: true }),
    ).toHaveValue("current");
    await expect(
      page.getByRole("checkbox", {
        name: "Offline: require existing dated cache",
      }),
    ).not.toBeChecked();
    await page.getByRole("button", { name: "Portfolio", exact: true }).click();
    await expect(
      page.getByRole("button", { name: "Create portfolio", exact: true }),
    ).toBeVisible();
    await expect(page.getByLabel("New portfolio name")).toBeVisible();
    await expect(page.locator("select")).toHaveCount(0);
    await page.getByRole("button", { name: "Settings", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: "Settings", exact: true }),
    ).toBeVisible();
    await page.getByRole("button", { name: "How to connect Steve" }).click();
    await expect(
      page.getByText("Connect the research analyst on your private server"),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  },
);
