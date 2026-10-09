import { test, expect } from "@playwright/test";
import { readFileSync } from "node:fs";

const tokenFile = process.env.SCANNER_TEST_TOKEN_FILE;
test.beforeEach(async ({ page }) => {
  if (!tokenFile)
    throw new Error(
      "Set SCANNER_TEST_TOKEN_FILE to a disposable private server token",
    );
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
  "theme and quiet-motion preferences survive reload without storing credentials",
  { tag: "@appearance" },
  async ({ page }) => {
    const original = await page.locator("html").getAttribute("data-theme");
    const next = original === "light" ? "dark" : "light";
    await page.getByRole("button", { name: `Switch to ${next} mode` }).click();
    await expect(page.locator("html")).toHaveAttribute("data-theme", next);
    await page
      .getByRole("button", { name: "Pause animations", exact: true })
      .click();
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
    await expect(page.locator(".brand .bowl-mark")).toHaveAttribute(
      "src",
      "/mascots/bowl-poster.webp",
    );
    await page.reload();
    await expect(
      page.getByRole("heading", { name: "Home", exact: true }),
    ).toBeVisible();
    await expect(page.locator("html")).toHaveAttribute("data-theme", next);
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
    const values = await page.evaluate(() => Object.entries(localStorage));
    expect(
      values.every(
        ([key, value]) =>
          ["cosoup.theme", "cosoup.motion"].includes(key) &&
          ["light", "dark", "on", "paused"].includes(value),
      ),
    ).toBe(true);
    await page
      .getByRole("button", { name: "Resume animations", exact: true })
      .click();
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    ).toBe(true);
  },
);

test(
  "device reduced motion keeps the conversation usable and switches to the static bowl",
  { tag: "@appearance" },
  async ({ page }) => {
    await expect(page.getByLabel("Message Steve")).toBeVisible();
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect(page.locator("html")).toHaveAttribute("data-motion", "off");
    await expect(
      page.getByRole("button", { name: "Resume animations", exact: true }),
    ).toBeDisabled();
    await expect(page.locator(".brand .bowl-mark")).toHaveAttribute(
      "src",
      "/mascots/bowl-poster.webp",
    );
    await expect(page.getByLabel("Message Steve")).toBeEditable();
    await page.emulateMedia({ reducedMotion: "no-preference" });
    await expect(page.locator("html")).toHaveAttribute("data-motion", "on");
    await expect(
      page.getByRole("button", { name: "Pause animations", exact: true }),
    ).toBeEnabled();
  },
);
