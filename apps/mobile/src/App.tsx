import { useEffect, useMemo, useState } from "react";
import {
  AppState,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  Text,
  View,
} from "react-native";
import { SafeAreaProvider, SafeAreaView } from "react-native-safe-area-context";
import * as SecureStore from "expo-secure-store";
import * as DocumentPicker from "expo-document-picker";
import * as ImagePicker from "expo-image-picker";
import {
  QueryClient,
  QueryClientProvider,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import {
  AgentRequest,
  ApiClient,
  Candidate,
  ContextPacket,
  ImportReview,
  Job,
  Period,
  Portfolio,
  Report,
  Scope,
  Transaction,
  reviewableRows,
  money,
  nativeServerUrl,
  pct,
  terminalStatuses,
} from "@stock-scanner/client";
import {
  useBars,
  useMovement,
  useWorkspace,
} from "@stock-scanner/client/queries";
import { colors, navigation, Page } from "@stock-scanner/design";
import {
  Button,
  ErrorBox,
  Field,
  Json,
  Metric,
  Panel,
  styles,
  Toggle,
} from "./components/UI";
import Candles from "./components/Candles";

const CREDENTIAL_KEY = "stock-scanner.owner";
const queries = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
    mutations: { retry: false },
  },
});
type Credentials = { origin: string; token: string };
export default function App() {
  return (
    <SafeAreaProvider>
      <QueryClientProvider client={queries}>
        <Connection />
      </QueryClientProvider>
    </SafeAreaProvider>
  );
}
function Connection() {
  const [credentials, setCredentials] = useState<Credentials | null>(null);
  const [origin, setOrigin] = useState("");
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const qc = useQueryClient();
  async function disconnect() {
    setCredentials(null);
    qc.clear();
    await SecureStore.deleteItemAsync(CREDENTIAL_KEY);
  }
  useEffect(() => {
    SecureStore.getItemAsync(CREDENTIAL_KEY)
      .then((v) => {
        if (v) {
          const c = JSON.parse(v) as Credentials;
          nativeServerUrl(c.origin);
          setCredentials(c);
        }
      })
      .catch(setError)
      .finally(() => setLoading(false));
  }, []);
  const api = useMemo(
    () =>
      new ApiClient({
        baseUrl: credentials?.origin,
        credential: async () => credentials?.token ?? null,
        onUnauthorized: () => {
          void disconnect();
        },
      }),
    [credentials],
  );
  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: colors.background }}>
      <KeyboardAvoidingView
        style={{ flex: 1 }}
        behavior={Platform.OS === "ios" ? "padding" : undefined}
      >
        {loading ? (
          <Text style={[styles.muted, { padding: 24 }]}>Connecting…</Text>
        ) : credentials ? (
          <Workspace api={api} disconnect={disconnect} />
        ) : (
          <ScrollView
            contentContainerStyle={[styles.page, { paddingTop: 50 }]}
            keyboardShouldPersistTaps="handled"
          >
            <Text style={styles.title}>CoSoup</Text>
            <Text style={styles.muted}>
              Private market research, portfolio and history.
            </Text>
            <Panel title="Connect to your home server">
              <Field
                label="Trusted HTTPS server origin"
                value={origin}
                onChange={setOrigin}
                placeholder="https://scanner.home.example"
              />
              <Field
                label="Owner token"
                value={token}
                onChange={setToken}
                secret
              />
              <Button
                title={busy ? "Connecting…" : "Connect"}
                disabled={busy || token.length < 32}
                onPress={async () => {
                  setBusy(true);
                  setError(null);
                  try {
                    const c = { origin: nativeServerUrl(origin), token };
                    const test = new ApiClient({
                      baseUrl: c.origin,
                      credential: async () => c.token,
                    });
                    await test.request("/me");
                    await SecureStore.setItemAsync(
                      CREDENTIAL_KEY,
                      JSON.stringify(c),
                      {
                        keychainAccessible:
                          SecureStore.WHEN_UNLOCKED_THIS_DEVICE_ONLY,
                      },
                    );
                    setCredentials(c);
                  } catch (e) {
                    setError(e);
                  } finally {
                    setToken("");
                    setBusy(false);
                  }
                }}
              />
              <ErrorBox error={error} />
              <Text style={styles.muted}>
                Credentials stay in the iOS Keychain. The server remains
                accessible through LAN/VPN with trusted HTTPS.
              </Text>
            </Panel>
          </ScrollView>
        )}
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
function Workspace({
  api,
  disconnect,
}: {
  api: ApiClient;
  disconnect: () => Promise<void>;
}) {
  const [page, setPage] = useState<Page>("Home");
  const data = useWorkspace(api);
  const qc = useQueryClient();
  useEffect(() => {
    const sub = AppState.addEventListener("change", (state) => {
      if (state === "active") qc.invalidateQueries();
    });
    return () => sub.remove();
  }, [qc]);
  const reports = data.reports.data ?? [],
    portfolios = data.portfolios.data ?? [],
    jobs = data.jobs.data ?? [];
  return (
    <>
      <View
        style={[
          styles.row,
          {
            padding: 16,
            borderBottomColor: colors.border,
            borderBottomWidth: 1,
          },
        ]}
      >
        <View>
          <Text style={styles.title}>
            {page === "More" ? "Operations" : page}
          </Text>
          <Text style={styles.muted}>
            {data.context.data?.latest_session ?? "Date unavailable"} · Market
            close data
          </Text>
        </View>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Disconnect"
          onPress={() => void disconnect()}
          style={{ minHeight: 44, justifyContent: "center" }}
        >
          <Text style={styles.muted}>Disconnect</Text>
        </Pressable>
      </View>
      <ScrollView
        contentContainerStyle={styles.page}
        keyboardShouldPersistTaps="handled"
      >
        <ErrorBox
          error={data.reports.error ?? data.portfolios.error ?? data.jobs.error}
        />
        {page === "Home" ? (
          <Home
            api={api}
            reports={reports}
            jobs={jobs}
            research={() => setPage("Research")}
          />
        ) : page === "Research" ? (
          <Research
            api={api}
            reports={reports}
            portfolios={portfolios}
            latest={data.context.data?.latest_session}
          />
        ) : page === "Portfolio" ? (
          <PortfolioScreen api={api} portfolios={portfolios} />
        ) : page === "Activity" ? (
          <Activity api={api} jobs={jobs} />
        ) : (
          <Operations api={api} reports={reports} portfolios={portfolios} />
        )}
      </ScrollView>
      <View
        style={{
          flexDirection: "row",
          borderTopColor: colors.border,
          borderTopWidth: 1,
        }}
      >
        {navigation.map((n) => (
          <Pressable
            key={n}
            accessibilityRole="tab"
            accessibilityState={{ selected: n === page }}
            onPress={() => setPage(n)}
            style={{
              flex: 1,
              minHeight: 58,
              alignItems: "center",
              justifyContent: "center",
            }}
          >
            <Text
              style={{
                color: n === page ? colors.accent : colors.muted,
                fontSize: 11,
              }}
            >
              {n}
            </Text>
          </Pressable>
        ))}
      </View>
    </>
  );
}
function useCommand(api: ApiClient) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>();
  const [result, setResult] = useState<unknown>();
  const [keys] = useState(() => new Map<string, string>());
  const qc = useQueryClient();
  async function run(path: string, body: unknown, method = "POST") {
    setBusy(true);
    setError(null);
    const signature = path + JSON.stringify(body);
    let key = keys.get(signature);
    if (!key) {
      key = `native-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      keys.set(signature, key);
    }
    try {
      const r = await api.request(path, method, body, key);
      keys.delete(signature);
      setResult(r);
      qc.invalidateQueries();
      return r;
    } catch (e) {
      setError(e);
      return undefined;
    } finally {
      setBusy(false);
    }
  }
  return { run, busy, error, result };
}
function CommandState({ command }: { command: ReturnType<typeof useCommand> }) {
  return (
    <>
      <ErrorBox error={command.error} />
      {command.result != null && <Json value={command.result} />}
    </>
  );
}
function Home({
  api,
  reports,
  jobs,
  research,
}: {
  api: ApiClient;
  reports: Report[];
  jobs: Job[];
  research: () => void;
}) {
  const command = useCommand(api);
  const [mode, setMode] = useState<"live" | "historical_snapshot">("live");
  const [start, setStart] = useState("");
  const [end, setEnd] = useState("");
  const [offline, setOffline] = useState("Offline");
  const [preview, setPreview] = useState<unknown>();
  const [signature, setSignature] = useState("");
  const [selected, setSelected] = useState("");
  const report = useQuery({
    queryKey: ["report", selected],
    queryFn: () => api.report(selected),
    enabled: !!selected,
  });
  const payload = {
    mode,
    research: "none",
    offline: offline === "Offline",
    ...(mode === "historical_snapshot" && start && end
      ? { start_date: start, end_date: end }
      : {}),
  };
  return (
    <>
      <Panel title="Your research workspace">
        <Text style={styles.muted}>
          {reports[0]?.data_date ?? "No reports"} ·{" "}
          {reports[0]?.quality ?? "Scan to begin"}
        </Text>
        <Text style={styles.text}>
          {jobs.filter((j) => !terminalStatuses.has(j.status)).length} active
          jobs
        </Text>
        <Button title="Open market workspace" onPress={research} />
      </Panel>
      <Panel title="Run a scan">
        <Toggle
          values={["live", "historical_snapshot"]}
          value={mode}
          onChange={setMode}
        />
        {mode === "historical_snapshot" && (
          <>
            <Field
              label="From (YYYY-MM-DD)"
              value={start}
              onChange={setStart}
            />
            <Field label="Through (YYYY-MM-DD)" value={end} onChange={setEnd} />
          </>
        )}
        <Toggle
          values={["Offline", "Missing only"]}
          value={offline}
          onChange={setOffline}
        />
        <Button
          title="Preview coverage"
          disabled={command.busy}
          onPress={async () => {
            const r = await command.run("/scan-plans", payload);
            if (r) {
              setPreview(r);
              setSignature(JSON.stringify(payload));
            }
          }}
        />
        {preview != null && <Json value={preview} />}
        <Button
          title="Queue scan"
          disabled={
            command.busy || signature !== JSON.stringify(payload) || !preview
          }
          onPress={() => void command.run("/scans", payload)}
        />
        <CommandState command={command} />
      </Panel>
      <Panel title="Reports">
        {reports.map((r) => (
          <Button
            key={r.id}
            title={`${r.data_date} · ${r.mode} · ${r.quality}`}
            onPress={() => setSelected(selected === r.id ? "" : r.id)}
          />
        ))}
        {!reports.length && (
          <Text style={styles.muted}>No reports available.</Text>
        )}
        <Text style={styles.muted}>
          Latest 100 reports. Use the web history or API pagination for older
          reports.
        </Text>
        <Button
          title="Queue weekly summary"
          disabled={command.busy}
          onPress={() => void command.run("/weekly-summaries", {})}
        />
        <ErrorBox error={report.error} />
        {report.data && <Json value={report.data} />}
      </Panel>
    </>
  );
}
function Research({
  api,
  reports,
  portfolios,
  latest,
}: {
  api: ApiClient;
  reports: Report[];
  portfolios: Portfolio[];
  latest?: string;
}) {
  const [scope, setScope] = useState<Scope>("candidates");
  const [period, setPeriod] = useState<Period>("1D");
  const [reportId, setReportId] = useState("");
  const [portfolioId, setPortfolioId] = useState("");
  const [selected, setSelected] = useState("");
  const report =
    reports.find(
      (r) =>
        r.id === reportId && ["live", "historical_snapshot"].includes(r.mode),
    ) ?? reports.find((r) => ["live", "historical_snapshot"].includes(r.mode));
  const portfolio =
    portfolios.find((p) => p.id === portfolioId) ?? portfolios[0];
  const date = scope === "portfolio" ? latest : report?.data_date;
  const movement = useMovement(
    api,
    scope,
    period,
    report?.id,
    portfolio?.id,
    date,
  );
  const bars = useBars(api, selected, date);
  const content = useQuery({
    queryKey: ["report", report?.id],
    queryFn: () => api.report(report!.id),
    enabled: !!report,
  });
  const item = movement.data?.items.find((i) => i.symbol === selected);
  const metrics = item?.metrics as Candidate | undefined;
  return selected ? (
    <Panel>
      <Button title="‹ Back to overview" onPress={() => setSelected("")} />
      <View style={styles.row}>
        <View>
          <Text style={styles.title}>{selected}</Text>
          <Text style={styles.muted}>{item?.name}</Text>
        </View>
        <View>
          <Text style={styles.title}>{money(item?.close)}</Text>
          <Text
            style={[
              styles.text,
              (item?.change_percent ?? 0) < 0
                ? styles.negative
                : styles.positive,
            ]}
          >
            {pct(item?.change_percent)} · {period}
          </Text>
        </View>
      </View>
      <ErrorBox error={bars.error} />
      {bars.data && <Candles data={bars.data} pivot={metrics?.pivot} />}{" "}
      {metrics && (
        <View style={{ flexDirection: "row", flexWrap: "wrap" }}>
          <Metric label="Breakout" value={money(metrics.pivot)} />
          <Metric
            label="Extension"
            value={pct(metrics.pivot_extension * 100)}
          />
          <Metric
            label="Relative volume"
            value={`${metrics.volume_ratio.toFixed(1)}x`}
          />
          <Metric
            label="Relative strength"
            value={`${(metrics.rs_excess * 100).toFixed(1)} pp`}
            note={`${content.data?.rules?.rs_days ?? 63} sessions vs SPY`}
          />
        </View>
      )}
      <Text style={styles.heading}>Research & sources</Text>
      <ErrorBox error={content.error} />
      <Json
        value={
          content.data?.research?.[selected] ?? {
            missing: "Company research unavailable for this report/symbol",
          }
        }
      />
    </Panel>
  ) : (
    <>
      <Toggle
        values={["portfolio", "candidates", "near_breakouts"]}
        value={scope}
        onChange={setScope}
      />
      <Toggle values={["1D", "1W", "1M"]} value={period} onChange={setPeriod} />
      {scope === "portfolio" ? (
        portfolios.map((p) => (
          <Button
            key={p.id}
            title={`${p.id === portfolio?.id ? "✓ " : ""}${p.name}`}
            onPress={() => setPortfolioId(p.id)}
          />
        ))
      ) : (
        <Panel title="Daily report">
          {reports
            .filter((r) => ["live", "historical_snapshot"].includes(r.mode))
            .slice(0, 5)
            .map((r) => (
              <Button
                key={r.id}
                title={`${r.id === report?.id ? "✓ " : ""}${r.data_date} · ${r.mode}`}
                onPress={() => setReportId(r.id)}
              />
            ))}
        </Panel>
      )}
      <Panel title="Daily movement">
        <Text style={styles.muted}>
          {date ?? "No daily report"} ·{" "}
          {movement.data?.quality ?? "No snapshot"}
        </Text>
        <Text style={styles.muted}>
          Close-to-close percentage price change. Native overview uses a
          readable 2D list; the web offers 3D.
        </Text>
        <ErrorBox error={movement.error} />
        {movement.isFetching && (
          <Text style={styles.muted}>Loading cached data…</Text>
        )}
        {movement.data?.items.map((i) => (
          <Pressable
            key={i.symbol}
            accessibilityRole="button"
            onPress={() => setSelected(i.symbol)}
            style={[
              styles.row,
              {
                minHeight: 64,
                borderBottomWidth: 1,
                borderBottomColor: colors.border,
              },
            ]}
          >
            <View style={{ flex: 1 }}>
              <Text style={styles.heading}>{i.symbol}</Text>
              <Text style={styles.muted}>{i.name ?? i.quality}</Text>
            </View>
            <Text style={styles.text}>{money(i.close)}</Text>
            <Text
              style={[
                styles.text,
                (i.change_percent ?? 0) < 0 ? styles.negative : styles.positive,
              ]}
            >
              {pct(i.change_percent)}
            </Text>
          </Pressable>
        ))}
        {movement.data && !movement.data.items.length && (
          <Text style={styles.muted}>
            No symbols in this scope. Inspect the report quality before
            interpreting an empty list.
          </Text>
        )}
      </Panel>
      {content.data && (
        <Panel title="Coverage & screening reasons">
          <Json
            value={{
              coverage: content.data.coverage,
              filter_counts: content.data.filter_counts,
              errors: content.data.errors,
            }}
          />
        </Panel>
      )}
    </>
  );
}
async function pickUpload(api: ApiClient, vision = false, camera = false) {
  let uri: string, name: string, type: string;
  if (vision) {
    if (camera) {
      const permission = await ImagePicker.requestCameraPermissionsAsync();
      if (!permission.granted)
        throw new Error("Camera permission is required to capture an image");
    }
    const result = camera
      ? await ImagePicker.launchCameraAsync({
          mediaTypes: ["images"],
          quality: 0.9,
        })
      : await ImagePicker.launchImageLibraryAsync({
          mediaTypes: ["images"],
          quality: 0.9,
        });
    if (result.canceled) return null;
    const asset = result.assets[0];
    uri = asset.uri;
    name = asset.fileName ?? "image.jpg";
    type = asset.mimeType ?? "image/jpeg";
  } else {
    const result = await DocumentPicker.getDocumentAsync({
      type: ["image/jpeg", "image/png", "application/pdf", "text/csv"],
      copyToCacheDirectory: true,
    });
    if (result.canceled) return null;
    const asset = result.assets[0];
    uri = asset.uri;
    name = asset.name;
    type = name.endsWith(".csv")
      ? "text/csv"
      : (asset.mimeType ?? "application/octet-stream");
  }
  const form = new FormData();
  form.append("file", { uri, name, type } as unknown as Blob);
  return api.upload(form);
}
function PortfolioScreen({
  api,
  portfolios,
}: {
  api: ApiClient;
  portfolios: Portfolio[];
}) {
  const [id, setId] = useState("");
  const portfolio = portfolios.find((p) => p.id === id) ?? portfolios[0];
  const command = useCommand(api);
  const [name, setName] = useState("");
  const [type, setType] = useState<Transaction["type"]>("buy");
  const [symbol, setSymbol] = useState("");
  const [quantity, setQuantity] = useState("");
  const [price, setPrice] = useState("");
  const [at, setAt] = useState("");
  const [amount, setAmount] = useState("");
  const [fees, setFees] = useState("0");
  const [importId, setImportId] = useState("");
  const [reviewRows, setReviewRows] = useState("[]");
  const [error, setError] = useState<unknown>();
  const [correctionId, setCorrectionId] = useState("");
  const ledger = useQuery({
    queryKey: ["positions", portfolio?.id],
    queryFn: () => api.positions(portfolio!.id),
    enabled: !!portfolio,
  });
  const transactions = useQuery({
    queryKey: ["transactions", portfolio?.id],
    queryFn: () =>
      api.request<Transaction[]>(`/portfolios/${portfolio!.id}/transactions`),
    enabled: !!portfolio,
  });
  const review = useQuery({
    queryKey: ["import", importId],
    queryFn: () => api.request<ImportReview>(`/imports/${importId}`),
    enabled: !!importId,
    refetchInterval: (q) => (q.state.data?.status === "queued" ? 3000 : false),
  });
  const share = ["buy", "sell", "opening", "split"].includes(type);
  return (
    <>
      <Panel title="Portfolio">
        {portfolios.map((p) => (
          <Button
            key={p.id}
            title={`${portfolio?.id === p.id ? "✓ " : ""}${p.name}`}
            onPress={() => setId(p.id)}
          />
        ))}
        <Field label="New portfolio name" value={name} onChange={setName} />
        <Button
          title="Create portfolio"
          disabled={!name || command.busy}
          onPress={() =>
            void command.run("/portfolios", { name, currency: "USD" })
          }
        />
        <CommandState command={command} />
      </Panel>
      {portfolio && (
        <>
          <Panel title="Supplied holdings">
            <ErrorBox error={ledger.error} />
            <Text style={styles.muted}>{ledger.data?.cash_note}</Text>
            {ledger.data?.positions.map((p) => (
              <View key={p.symbol} style={styles.row}>
                <Text style={styles.heading}>{p.symbol}</Text>
                <Text style={styles.text}>
                  {p.quantity} shares · Basis {money(p.cost_basis)}
                </Text>
              </View>
            ))}
            <Text style={styles.muted}>
              Reconstructed cash {money(ledger.data?.cash)} · Known realized P&L{" "}
              {money(ledger.data?.realized_pnl)}
            </Text>
            <Button
              title="Queue closing valuation"
              disabled={command.busy}
              onPress={() =>
                void command.run(
                  `/portfolios/${portfolio.id}/analysis-jobs`,
                  {},
                )
              }
            />
          </Panel>
          <Panel title={correctionId ? "Audited correction" : "Journal entry"}>
            <Toggle
              values={
                [
                  "buy",
                  "sell",
                  "opening",
                  "deposit",
                  "withdrawal",
                  "dividend",
                  "fee",
                  "split",
                ] as const
              }
              value={type}
              onChange={setType}
            />
            <Field
              label="Actual timestamp with timezone"
              value={at}
              onChange={setAt}
              placeholder="2026-10-02T15:00:00-04:00"
            />
            {share ? (
              <>
                <Field label="Symbol" value={symbol} onChange={setSymbol} />
                <Field
                  label={type === "split" ? "Split factor" : "Quantity"}
                  value={quantity}
                  onChange={setQuantity}
                />
                {type !== "split" && (
                  <Field
                    label="Actual unit price (blank opening basis = unknown)"
                    value={price}
                    onChange={setPrice}
                  />
                )}
              </>
            ) : (
              <Field label="Amount (USD)" value={amount} onChange={setAmount} />
            )}
            <Field label="Fees (USD)" value={fees} onChange={setFees} />
            <Button
              title={correctionId ? "Save correction" : "Record entry"}
              disabled={command.busy}
              onPress={() => {
                const payload = {
                  type,
                  at,
                  currency: "USD",
                  fees: type === "split" ? "0" : fees,
                  ...(share
                    ? {
                        symbol: symbol.toUpperCase(),
                        quantity,
                        ...(price && type !== "split" ? { price } : {}),
                      }
                    : { amount }),
                };
                void command.run(
                  `/portfolios/${portfolio.id}/transactions${correctionId ? `/${correctionId}/corrections` : ""}`,
                  payload,
                );
              }}
            />
            {correctionId && (
              <Button
                title="Cancel correction"
                onPress={() => setCorrectionId("")}
              />
            )}
          </Panel>
          <Panel title="Import & review">
            <Button
              title="Choose document / image"
              disabled={command.busy}
              onPress={async () => {
                try {
                  const upload = await pickUpload(api);
                  if (upload) {
                    const r = (await command.run("/imports", {
                      portfolio_id: portfolio.id,
                      upload_id: upload.upload_id,
                    })) as { import_id: string } | undefined;
                    if (r) setImportId(r.import_id);
                  }
                } catch (e) {
                  setError(e);
                }
              }}
            />
            <Field
              label="Import ID (resume review)"
              value={importId}
              onChange={setImportId}
            />
            <ErrorBox error={error ?? review.error} />
            {review.data && (
              <>
                <Text style={styles.muted}>Status: {review.data.status}</Text>
                <Json value={review.data.proposal} />
                {review.data.status === "awaiting_review" && (
                  <>
                    <Button
                      title="Copy proposals to editor"
                      onPress={() =>
                        setReviewRows(
                          JSON.stringify(
                            reviewableRows(review.data!.proposal.rows ?? []),
                            null,
                            2,
                          ),
                        )
                      }
                    />
                    <Field
                      label="Reviewed transaction rows (JSON)"
                      value={reviewRows}
                      onChange={setReviewRows}
                      multiline
                    />
                    <Button
                      title="Confirm reviewed rows"
                      disabled={command.busy}
                      onPress={() => {
                        try {
                          void command.run(`/imports/${importId}/confirm`, {
                            rows: JSON.parse(reviewRows),
                          });
                        } catch (e) {
                          setError(e);
                        }
                      }}
                    />
                    <Button
                      title="Reject import"
                      disabled={command.busy}
                      onPress={() =>
                        void command.run(`/imports/${importId}/reject`, {})
                      }
                    />
                  </>
                )}
              </>
            )}
          </Panel>
          <Panel title="Journal">
            <ErrorBox error={transactions.error} />
            {transactions.data?.map((tx) => (
              <View
                key={tx.id}
                style={{
                  gap: 8,
                  borderBottomWidth: 1,
                  borderBottomColor: colors.border,
                  paddingVertical: 12,
                }}
              >
                <Text style={styles.text}>
                  {tx.type} {tx.symbol} · {tx.quantity ?? tx.amount}{" "}
                  {tx.price ? `@ ${money(tx.price)}` : ""}
                </Text>
                <Text style={styles.muted}>
                  {tx.at} · {tx.superseded ? "Superseded" : "Active"}
                </Text>
                {!tx.superseded && (
                  <Button
                    title="Correct this entry"
                    onPress={() => {
                      setCorrectionId(tx.id!);
                      setType(tx.type);
                      setAt(tx.at);
                      setSymbol(tx.symbol ?? "");
                      setQuantity(tx.quantity ?? "");
                      setPrice(tx.price ?? "");
                      setAmount(tx.amount ?? "");
                      setFees(tx.fees);
                    }}
                  />
                )}
              </View>
            ))}
            <Text style={styles.muted}>
              First 100 entries; full pagination is available on web/API.
            </Text>
          </Panel>
        </>
      )}
    </>
  );
}
function Activity({ api, jobs }: { api: ApiClient; jobs: Job[] }) {
  const [id, setId] = useState("");
  const job = jobs.find((j) => j.id === id) ?? jobs[0];
  const command = useCommand(api);
  const events = useQuery({
    queryKey: ["events", job?.id],
    queryFn: () => api.request(`/jobs/${job!.id}/events`),
    enabled: !!job,
    refetchInterval: job && !terminalStatuses.has(job.status) ? 5000 : false,
  });
  return (
    <>
      <Panel title="Durable jobs">
        {jobs.map((j) => (
          <Button
            key={j.id}
            title={`${j.kind} · ${j.status}`}
            onPress={() => setId(j.id)}
          />
        ))}
        <Text style={styles.muted}>
          Latest 100 jobs. Closing the app does not stop server work.
        </Text>
      </Panel>
      {job && (
        <Panel title={`${job.kind} · ${job.status}`}>
          <Json
            value={{
              id: job.id,
              error: job.error,
              progress: job.progress,
              result: job.result,
            }}
          />
          {!terminalStatuses.has(job.status) && (
            <Button
              title="Cancel cooperatively"
              disabled={command.busy || job.cancel_requested}
              onPress={() => void command.run(`/jobs/${job.id}/cancel`, {})}
            />
          )}{" "}
          {["failed", "cancelled", "waiting_for_archive"].includes(
            job.status,
          ) && (
            <Button
              title="Resume after resolving cause"
              disabled={command.busy}
              onPress={() => void command.run(`/jobs/${job.id}/resume`, {})}
            />
          )}
          <CommandState command={command} />
          <ErrorBox error={events.error} />
          <Json value={events.data} />
        </Panel>
      )}
    </>
  );
}
function Operations({
  api,
  reports,
  portfolios,
}: {
  api: ApiClient;
  reports: Report[];
  portfolios: Portfolio[];
}) {
  const status = useQuery({
    queryKey: ["status"],
    queryFn: () => api.status(),
  });
  const command = useCommand(api);
  const [prompt, setPrompt] = useState("");
  const [type, setType] = useState<AgentRequest["task_type"]>("daily_review");
  const [portfolio, setPortfolio] = useState("");
  const [consent, setConsent] = useState("No export");
  const [images, setImages] = useState<string[]>([]);
  const [imageConsent, setImageConsent] = useState("No image export");
  const [context, setContext] = useState<ContextPacket>();
  const [error, setError] = useState<unknown>();
  const [end, setEnd] = useState("");
  const [start, setStart] = useState("");
  const [report, setReport] = useState("");
  const [schedule, setSchedule] = useState(
    '{"name":"Daily research","trigger":{"type":"market_close"},"task":{"type":"daily_scan"},"missed_run_policy":"run_once","enabled":false}',
  );
  const [policy, setPolicy] = useState(
    '{"archive_after_days":31,"archive_evict":false}',
  );
  const [restore, setRestore] = useState("");
  const schedules = useQuery({
    queryKey: ["schedules"],
    queryFn: () =>
      api.request<
        { id: string; name: string; enabled: boolean; next_at: string | null }[]
      >("/schedules"),
  });
  const storage = useQuery({
    queryKey: ["storage"],
    queryFn: () => api.request("/storage/status"),
  });
  const request: AgentRequest = {
    task_type: type,
    prompt: prompt || "Review selected context",
    allow_portfolio_data: consent === "Authorize portfolio export",
    allow_uploaded_documents: imageConsent === "Authorize image export",
    upload_ids: images,
    ...(portfolio ? { portfolio_id: portfolio } : {}),
    ...(start ? { start_date: start } : {}),
    ...(end ? { end_date: end } : {}),
    ...(report ? { report_ids: [report] } : {}),
  };
  async function image(camera = false) {
    try {
      const uploaded = await pickUpload(api, true, camera);
      if (uploaded)
        setImages((old) => [...old, uploaded.upload_id].slice(0, 4));
    } catch (e) {
      setError(e);
    }
  }
  return (
    <>
      <Panel title="Research analyst">
        <Text style={styles.badge}>
          {status.data?.capabilities.codex ?? "Unknown"}
        </Text>
        <Toggle
          values={
            [
              "daily_review",
              "weekly_review",
              "portfolio_review",
              "document_review",
            ] as const
          }
          value={type}
          onChange={setType}
        />
        <Field
          label="Your question"
          value={prompt}
          onChange={setPrompt}
          multiline
          placeholder="Compare this week's candidates and identify research gaps."
        />
        <Field
          label="From (optional YYYY-MM-DD)"
          value={start}
          onChange={setStart}
        />
        <Field
          label="Through (optional YYYY-MM-DD)"
          value={end}
          onChange={setEnd}
        />
        <Field
          label="Selected report ID (optional)"
          value={report}
          onChange={setReport}
        />
        <Field
          label="Portfolio ID (optional)"
          value={portfolio}
          onChange={setPortfolio}
        />
        {portfolios.map((p) => (
          <Button
            key={p.id}
            title={`Select ${p.name}`}
            onPress={() => setPortfolio(p.id)}
          />
        ))}
        <Toggle
          values={["No export", "Authorize portfolio export"]}
          value={consent}
          onChange={setConsent}
        />
        <Button
          title="Attach image for vision"
          disabled={images.length >= 4}
          onPress={() => void image()}
        />
        <Button
          title="Capture image for vision"
          disabled={images.length >= 4}
          onPress={() => void image(true)}
        />
        <Text style={styles.muted}>{images.length} image(s) attached</Text>
        {images.length > 0 && (
          <Button title="Clear attachments" onPress={() => setImages([])} />
        )}
        <Toggle
          values={["No image export", "Authorize image export"]}
          value={imageConsent}
          onChange={setImageConsent}
        />
        <Button
          title="Preview structured context"
          disabled={command.busy}
          onPress={async () => {
            try {
              setContext(await api.context(request));
            } catch (e) {
              setError(e);
            }
          }}
        />
        {context && <Json value={context} />}
        <Button
          title="Queue analysis"
          disabled={
            command.busy ||
            !prompt.trim() ||
            status.data?.capabilities.codex !== "operator_verified" ||
            (!!portfolio && !request.allow_portfolio_data) ||
            (images.length > 0 && !request.allow_uploaded_documents)
          }
          onPress={() => void command.run("/agent/tasks", request)}
        />
        <ErrorBox error={error ?? status.error} />
        <CommandState command={command} />
        <Text style={styles.muted}>
          Authorized sources only. JPEG/PNG vision; PDF/CSV use reviewed
          imports. No automatic journal changes.
        </Text>
      </Panel>
      <Panel title="Schedules">
        <Field
          label="New schedule (JSON)"
          value={schedule}
          onChange={setSchedule}
          multiline
        />
        <Button
          title="Create schedule"
          disabled={command.busy}
          onPress={() => {
            try {
              void command.run("/schedules", JSON.parse(schedule));
            } catch (e) {
              setError(e);
            }
          }}
        />
        {schedules.data?.map((s) => (
          <View key={s.id} style={{ gap: 8 }}>
            <Text style={styles.text}>
              {s.name} · {s.enabled ? "Enabled" : "Disabled"} ·{" "}
              {s.next_at ?? "No next run"}
            </Text>
            <Button
              title={s.enabled ? "Disable" : "Enable"}
              disabled={command.busy}
              onPress={() =>
                void command.run(
                  `/schedules/${s.id}`,
                  { enabled: !s.enabled },
                  "PATCH",
                )
              }
            />
            <Button
              title="Run now"
              disabled={command.busy}
              onPress={() => void command.run(`/schedules/${s.id}/run-now`, {})}
            />
          </View>
        ))}
        <ErrorBox error={schedules.error} />
      </Panel>
      <Panel title="Storage & retention">
        <ErrorBox error={storage.error} />
        <Json value={storage.data} />
        <Field
          label="Retention overrides (JSON)"
          value={policy}
          onChange={setPolicy}
          multiline
        />
        <Button
          title="Save retention policy"
          disabled={command.busy}
          onPress={() => {
            try {
              void command.run("/storage/policy", JSON.parse(policy), "PATCH");
            } catch (e) {
              setError(e);
            }
          }}
        />
        <Button
          title="Queue archive batch"
          disabled={command.busy}
          onPress={() => void command.run("/storage/archive-jobs", {})}
        />
        <Field
          label="Restore artifact IDs (comma-separated)"
          value={restore}
          onChange={setRestore}
        />
        <Button
          title="Queue bounded restore"
          disabled={command.busy || !restore.trim()}
          onPress={() =>
            void command.run("/storage/restore-jobs", {
              artifact_ids: restore
                .split(",")
                .map((s) => s.trim())
                .filter(Boolean),
            })
          }
        />
      </Panel>
    </>
  );
}
