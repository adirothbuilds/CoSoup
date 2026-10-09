import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";
const cid = "f".repeat(32),
  iid = "e".repeat(32),
  uid = "d".repeat(32),
  jid = "c".repeat(32),
  pid = "b".repeat(32);
async function connect(page: any) {
  const file = process.env.SCANNER_TEST_TOKEN_FILE;
  if (!file) throw new Error("A private local token file is required");
  await page.goto("/");
  await page.getByLabel("Owner token").fill(readFileSync(file, "utf8").trim());
  await page.getByRole("button", { name: "Connect to private server" }).click();
  await expect(
    page.getByRole("heading", { name: "Home", exact: true }),
  ).toBeVisible();
}
test(
  "synthetic chat chart and reviewed portfolio entries survive reload without a real journal write",
  { tag: "@chat-fixture" },
  async ({ page }) => {
    let saved = false;
    let confirmed: any;
    await page.route("**/api/v1/imports/" + iid, (route) =>
      route.fulfill({
        json: {
          id: iid,
          status: saved ? "confirmed" : "awaiting_review",
          portfolio_id: pid,
          proposal: {},
          confirmed_ids: [],
        },
      }),
    );
    await page.route("**/api/v1/imports/" + iid + "/confirm", async (route) => {
      confirmed = route.request().postDataJSON();
      saved = true;
      await route.fulfill({
        json: { transaction_ids: ["synthetic-confirmation"] },
      });
    });
    await page.route("**/api/v1/agent/conversations/" + cid, (route) =>
      route.fulfill({
        json: {
          id: cid,
          messages: [
            {
              job_id: jid,
              prompt: "Explain this synthetic fixture",
              status: "succeeded",
              import_ids: [iid],
              document_export_authorized: true,
              answer: {
                markdown:
                  "## Synthetic evidence\nA chart and a draft; no journal entries have been applied.",
                sources: [iid],
                gaps: ["Synthetic data only"],
                data_date: "2026-10-08",
                charts: [
                  {
                    id: "synthetic-chart",
                    source_id: uid,
                    title: "Synthetic comparison",
                    kind: "bar",
                    unit: "×",
                    points: [
                      { label: "ABC", value: 1.5 },
                      { label: "XYZ", value: 2 },
                    ],
                    note: "Synthetic fixture; not real market data.",
                  },
                ],
                portfolio_proposals: [
                  {
                    import_id: iid,
                    warnings: ["Timestamp and currency require review."],
                    rows: [
                      {
                        type: "opening",
                        symbol: "ABC",
                        quantity: "10",
                        price: null,
                        amount: null,
                        at: null,
                        fees: null,
                        currency: null,
                        source_text: "Synthetic statement: ABC 10 shares",
                      },
                    ],
                  },
                ],
              },
            },
          ],
        },
      }),
    );
    await connect(page);
    await page.goto("/?chat=" + cid + "#home");
    await expect(
      page.getByRole("figure").filter({ hasText: "Synthetic comparison" }),
    ).toBeVisible();
    await page
      .getByRole("button", { name: "Save reviewed entries", exact: true })
      .click();
    await expect(
      page.getByText(
        "Review the timestamp, currency and fees for every entry.",
        { exact: true },
      ),
    ).toBeVisible();
    expect(confirmed).toBeUndefined();
    const review = page.getByRole("region", {
      name: "Review proposed portfolio entries",
    });
    await review
      .getByLabel("Actual timestamp with timezone")
      .fill("2026-10-02T12:00:00+00:00");
    await review.getByRole("combobox", { name: "Currency", exact: true }).selectOption("USD");
    await review.getByLabel("Fees", { exact: true }).fill("0");
    await page
      .getByRole("button", { name: "Save reviewed entries", exact: true })
      .click();
    await expect(
      page.getByText("Saved to your portfolio", { exact: true }),
    ).toBeVisible();
    expect(confirmed.rows[0]).toMatchObject({
      type: "opening",
      quantity: "10",
      price: null,
      currency: "USD",
      fees: "0",
    });
    expect(confirmed.rows[0]).not.toHaveProperty("source_text");
    await page.reload();
    await expect(
      page.getByText("Saved to your portfolio", { exact: true }),
    ).toBeVisible();
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  },
);
test(
  "synthetic attachment requires explicit sharing and creates one chat turn",
  { tag: "@chat-fixture" },
  async ({ page }) => {
    let submission: any;
    await page.route("**/api/v1/portfolios", (route) =>
      route.fulfill({
        json: [{ id: pid, name: "Synthetic destination", currency: "USD" }],
      }),
    );
    await page.route("**/api/v1/uploads", (route) =>
      route.fulfill({ status: 201, json: { upload_id: uid } }),
    );
    await page.route("**/api/v1/imports", (route) =>
      route.fulfill({ status: 202, json: { import_id: iid, job_id: jid } }),
    );
    await page.route("**/api/v1/jobs/" + jid, (route) =>
      route.fulfill({ json: { id: jid, status: "succeeded" } }),
    );
    await page.route("**/api/v1/imports/" + iid, (route) =>
      route.fulfill({
        json: {
          id: iid,
          status: "awaiting_review",
          proposal: { rows: [] },
          confirmed_ids: [],
        },
      }),
    );
    await page.route("**/api/v1/agent/conversations/*", (route) =>
      route.fulfill({
        json: {
          id: submission?.conversation_id,
          messages: submission
            ? [
                {
                  job_id: jid,
                  prompt: submission.prompt,
                  status: "queued",
                  answer: null,
                  document_export_authorized: true,
                },
              ]
            : [],
        },
      }),
    );
    await page.route("**/api/v1/agent/chat", async (route) => {
      expect(submission).toBeUndefined();
      submission = route.request().postDataJSON();
      await route.fulfill({
        status: 202,
        json: { job_id: jid, status: "queued" },
      });
    });
    await connect(page);
    await expect(page.locator(".chat-context")).not.toHaveAttribute("open");
    await expect(page.locator(".background-work")).not.toHaveAttribute("open");
    await page
      .getByRole("button", { name: "Attach documents", exact: true })
      .click();
    await page
      .getByLabel("Attach screenshots or documents")
      .setInputFiles({
        name: "synthetic.png",
        mimeType: "image/png",
        buffer: Buffer.from(
          "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a0yYAAAAASUVORK5CYII=",
          "base64",
        ),
      });
    await expect(
      page.getByText("synthetic.png · Ready for Steve", { exact: false }),
    ).toBeVisible();
    await page
      .getByLabel("Message Steve")
      .fill("Use this synthetic screenshot to prepare entries for review");
    await expect(
      page.getByRole("button", { name: "Send to Steve", exact: true }),
    ).toBeDisabled();
    await page
      .getByLabel("Share attachments and prior document context with codex", {
        exact: true,
      })
      .check();
    await page
      .getByRole("button", { name: "Send to Steve", exact: true })
      .click();
    await expect(
      page.getByRole("button", { name: "Send to Steve", exact: true }),
    ).toBeDisabled();
    expect(submission).toMatchObject({
      upload_ids: [uid],
      import_ids: [iid],
      allow_uploaded_documents: true,
      allow_portfolio_data: false,
    });
    expect(
      await page.evaluate(() =>
        Object.keys(localStorage).every((k) =>
          ["cosoup.theme", "cosoup.motion"].includes(k),
        ),
      ),
    ).toBe(true);
  },
);
