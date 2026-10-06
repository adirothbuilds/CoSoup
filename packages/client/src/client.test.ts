import { describe, it, expect, vi } from "vitest";
import {
  ApiClient,
  ApiError,
  barsSchema,
  movementSchema,
  nativeServerUrl,
  pct,
  safeSource,
  usableDailyReport,
  researchState,
  Report,
} from "./index";
describe("shared contracts and private transport", () => {
  it("aborts a stalled request without automatically resubmitting a mutation", async () => {
    vi.useFakeTimers();
    try {
      let signal: AbortSignal | undefined;
      const fetcher = vi.fn((_url: unknown, options?: RequestInit) => {
        signal = options?.signal as AbortSignal;
        return new Promise<Response>(() => {});
      }) as unknown as typeof fetch;
      const api = new ApiClient({ fetcher, requestTimeoutMs: 15000 });
      const outcome = expect(
        api.request("/scans", "POST", { offline: true }, "same-intent"),
      ).rejects.toMatchObject({ code: "request_timeout" });
      await vi.advanceTimersByTimeAsync(15000);
      await outcome;
      expect(signal?.aborted).toBe(true);
      expect(fetcher).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });
  it("bounds connection and response-body waits as well as fetching headers", async () => {
    vi.useFakeTimers();
    try {
      const fetcher = vi.fn(async () => ({
        ok: true,
        json: () => new Promise(() => {}),
        text: () => new Promise(() => {}),
      })) as unknown as typeof fetch;
      const api = new ApiClient({ fetcher, requestTimeoutMs: 15 });
      for (const read of [
        () => api.connect("test-private-token"),
        () => api.request("/reports/example/content"),
        () => api.markdown("example"),
      ]) {
        const outcome = expect(read()).rejects.toMatchObject({
          code: "request_timeout",
        });
        await vi.advanceTimersByTimeAsync(15);
        await outcome;
      }
      expect(fetcher).toHaveBeenCalledTimes(3);
    } finally {
      vi.useRealTimers();
    }
  });
  it("prefers usable reports while preserving an explicit blocked-report selection", () => {
    const blocked = {
      id: "blocked",
      mode: "live",
      quality: "blocked_provider",
    } as Report;
    const usable = {
      id: "good",
      mode: "live",
      quality: "partial_coverage",
    } as Report;
    expect(usableDailyReport([blocked, usable])?.id).toBe("good");
    expect(usableDailyReport([blocked, usable], "blocked")?.id).toBe("blocked");
    expect(usableDailyReport([blocked, usable], "expired-id")?.id).toBe("good");
    expect(usableDailyReport([blocked])?.id).toBe("blocked");
  });
  it("distinguishes disabled research, source blocking and unknown legacy runs", () => {
    expect(
      researchState({
        data_date: "2026-10-02",
        status: "complete",
        warnings: [
          "Current-source research was not run; technical screening is not company research",
        ],
      }),
    ).toBe("not_run");
    expect(
      researchState({ data_date: "2026-10-02", status: "blocked_provider" }),
    ).toBe("blocked");
    expect(
      researchState({
        data_date: "2026-10-02",
        status: "complete",
        research_run: {
          requested: true,
          status: "offline_unavailable",
          checked_symbols: [],
          limit: 5,
        },
      }),
    ).toBe("offline_unavailable");
    expect(researchState({ data_date: "2026-10-02", status: "complete" })).toBe(
      "unknown",
    );
  });
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
