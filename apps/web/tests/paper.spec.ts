import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

test(
  "paper experiment charts and pause state survive reload without a real ledger write",
  { tag: "@paper-fixture" },
  async ({ page }) => {
    const file = process.env.SCANNER_TEST_TOKEN_FILE;
    if (!file) throw new Error("A private local token reference is required");
    const id = "9".repeat(32);
    let status = "active",
      writes = 0;
    const charts = ["agent", "spy", "scanner"].map((label, i) => ({
      id: id + ":" + label,
      source_id: id,
      title: "Synthetic " + label + " equity",
      kind: "line",
      unit: "USD",
      points: [
        { label: "2026-10-09", value: 100000 },
        { label: "2026-10-12", value: [102000, 110000, 100000][i] },
      ],
      note: "Synthetic fixture; no real portfolio or trading return.",
    }));
    await page.route("**/api/v1/paper/experiments", (route) =>
      route.fulfill({
        json: [
          {
            id,
            name: "Synthetic paper experiment",
            status,
            start_date: "2026-10-09",
            starting_equity: "100000",
            note: "Synthetic prospective accounting fixture.",
            policy: {
              max_positions: 10,
              max_position_weight: "0.2",
              execution: "Future daily-bar open",
            },
            books: {
              agent: { cash: "80000", positions: { ABC: "2000" }, fills: [] },
            },
            pending: {
              agent: {
                session: "2026-10-12",
                status: "filled",
                weights: { ABC: "0.2" },
              },
            },
            snapshots: [
              {
                session: "2026-10-12",
                quality: "complete",
                books: {
                  agent: {
                    equity: "102000",
                    cash: "80000",
                    change_pct: 2,
                    drawdown_pct: 0,
                    cost_sensitivity_equity: "101980",
                  },
                },
              },
            ],
            decisions: [],
            gaps: [],
            charts,
          },
        ],
      }),
    );
    await page.route("**/api/v1/paper/experiments/" + id, async (route) => {
      expect(route.request().method()).toBe("PATCH");
      writes++;
      status = route.request().postDataJSON().status;
      await route.fulfill({ json: { status } });
    });
    await page.goto("/");
    await page
      .getByLabel("Owner token")
      .fill(readFileSync(file, "utf8").trim());
    await page
      .getByRole("button", { name: "Connect to private server" })
      .click();
    await expect(
      page.getByRole("heading", { name: "Home", exact: true }),
    ).toBeVisible();
    await page.goto("/?paper=" + id + "#home");
    const panel = page.getByRole("region", {
      name: "Synthetic paper experiment",
    });
    await expect(
      panel.getByText("Price-only change", { exact: true }),
    ).toBeVisible();
    await expect(panel.locator(".chat-chart")).toHaveCount(3);
    await panel.getByRole("button", { name: "Pause new decisions" }).click();
    await expect(
      panel.getByRole("button", { name: "Resume decisions" }),
    ).toBeVisible();
    await page.reload();
    await expect(
      panel.getByRole("button", { name: "Resume decisions" }),
    ).toBeVisible();
    expect(writes).toBe(1);
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth + 1,
      ),
    ).toBe(false);
  },
);
