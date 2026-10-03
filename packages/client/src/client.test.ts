import { describe, it, expect, vi } from "vitest";
import {
  ApiClient,
  ApiError,
  barsSchema,
  movementSchema,
  nativeServerUrl,
  pct,
  safeSource,
} from "./index";
describe("shared contracts and private transport", () => {
  it("keeps unavailable movement distinct from zero", () => {
    const m = movementSchema.parse({
      data_date: "2026-10-02",
      start_date: "2026-10-01",
      period: "1D",
      basis: "split_adjusted",
      items: [
        {
          symbol: "AVT",
          change_percent: null,
          close: null,
          quality: "missing_sessions",
        },
      ],
      total_symbols: 1,
      displayed_symbols: 1,
      quality: "partial_coverage",
      restore_artifact_ids: [],
    });
    expect(pct(m.items[0].change_percent)).toBe("Unavailable");
    expect(pct(0)).toBe("0.0%");
  });
  it("rejects malformed numeric chart contracts", () => {
    expect(() => barsSchema.parse({ bars: [{ close: "12" }] })).toThrow();
  });
  it("protects native origin and source protocols", () => {
    expect(nativeServerUrl("https://scanner.example")).toBe(
      "https://scanner.example",
    );
    expect(() => nativeServerUrl("http://scanner.example")).toThrow();
    expect(() =>
      nativeServerUrl("https://owner:token@scanner.example"),
    ).toThrow();
    expect(safeSource("javascript:alert(1)")).toBeNull();
  });
  it("uses cookies and CSRF without persisting the owner token", async () => {
    const calls: RequestInit[] = [];
    const fetcher = vi.fn(async (_url: unknown, options?: RequestInit) => {
      calls.push(options!);
      return new Response(
        JSON.stringify(
          calls.length === 1
            ? {
                owner_id: "owner",
                csrf_token: "csrf",
                expires_at: "2026-10-03",
              }
            : { ok: true },
        ),
        { status: 200, headers: { "Content-Type": "application/json" } },
      );
    }) as unknown as typeof fetch;
    const api = new ApiClient({ fetcher });
    await api.connect("private-test-token");
    await api.request("/portfolios", "POST", { name: "Test" }, "intent");
    expect((calls[0].headers as Record<string, string>).Authorization).toBe(
      "Bearer private-test-token",
    );
    expect(
      (calls[1].headers as Record<string, string>).Authorization,
    ).toBeUndefined();
    expect((calls[1].headers as Record<string, string>)["X-Scanner-CSRF"]).toBe(
      "csrf",
    );
    expect(calls[1].credentials).toBe("include");
  });
  it("uses the native credential adapter without browser cookies", async () => {
    const fetcher = vi.fn(
      async () => new Response("{}", { status: 200 }),
    ) as unknown as typeof fetch;
    const api = new ApiClient({
      baseUrl: "https://scanner.example",
      credential: async () => "keychain-test-token",
      fetcher,
    });
    await api.request("/me");
    const options = (fetcher as ReturnType<typeof vi.fn>).mock.calls[0][1];
    expect(options.credentials).toBe("omit");
    expect(options.headers.Authorization).toBe("Bearer keychain-test-token");
  });
  it("preserves exact provider errors and never retries requests", async () => {
    const fetcher = vi.fn(
      async () =>
        new Response(
          JSON.stringify({
            error: {
              code: "restore_required",
              message: "Restore before proceeding",
            },
          }),
          { status: 409 },
        ),
    ) as unknown as typeof fetch;
    const api = new ApiClient({ fetcher });
    await expect(api.request("/reports/private/content")).rejects.toMatchObject(
      { status: 409, code: "restore_required" },
    );
    expect(fetcher).toHaveBeenCalledTimes(1);
  });
});
