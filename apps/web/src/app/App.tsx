import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  Activity as ActivityIcon,
  BarChart3,
  ChevronRight,
  Home as HomeIcon,
  MoreHorizontal,
  Wallet,
  LogOut,
  Server,
} from "lucide-react";
import { ApiClient } from "@stock-scanner/client";
import { useWorkspace } from "@stock-scanner/client/queries";
import { navigation, Page } from "@stock-scanner/design";
import { ErrorBox } from "../components/UI";
import Research from "../features/research/Research";
import Portfolio from "../features/portfolio/Portfolio";
import Activity from "../features/activity/Activity";
import Home from "../features/overview/Home";
import Operations from "../features/operations/Operations";

export default function App() {
  const qc = useQueryClient();
  const [connected, setConnected] = useState(false);
  const [checking, setChecking] = useState(true);
  const [token, setToken] = useState("");
  const [error, setError] = useState<unknown>();
  const [busy, setBusy] = useState(false);
  const api = useMemo(
    () =>
      new ApiClient({
        onUnauthorized: () => {
          setConnected(false);
          qc.clear();
        },
      }),
    [qc],
  );
  useEffect(() => {
    api
      .session()
      .then(() => setConnected(true))
      .catch(() => {})
      .finally(() => setChecking(false));
  }, [api]);
  if (checking)
    return (
      <div className="connect-shell">
        <p>Connecting to your private server…</p>
      </div>
    );
  if (!connected)
    return (
      <main className="connect-shell">
        <div className="connect-card">
          <BarChart3 size={36} />
          <p className="eyebrow">PRIVATE RESEARCH</p>
          <h1>Stock Scanner</h1>
          <p className="muted">
            Your market research, portfolio and history in one quiet workspace.
          </p>
          <form
            onSubmit={async (e) => {
              e.preventDefault();
              setBusy(true);
              setError(null);
              try {
                await api.connect(token);
                setConnected(true);
              } catch (e) {
                setError(e);
              } finally {
                setToken("");
                setBusy(false);
              }
            }}
          >
            <label>
              Owner token
              <input
                type="password"
                autoComplete="off"
                value={token}
                onChange={(e) => setToken(e.target.value)}
                required
                minLength={32}
              />
            </label>
            <button className="primary" disabled={busy}>
              {busy ? "Connecting…" : "Connect to private server"}
              <ChevronRight size={18} />
            </button>
          </form>
          <ErrorBox error={error} />
          <p className="muted small">
            Token is exchanged for a protected session and cleared from the
            form. Access stays on your LAN/VPN.
          </p>
        </div>
      </main>
    );
  return (
    <Workspace
      api={api}
      logout={async () => {
        try {
          await api.disconnect();
        } finally {
          setConnected(false);
          qc.clear();
        }
      }}
    />
  );
}
const icons = {
  Home: HomeIcon,
  Research: BarChart3,
  Portfolio: Wallet,
  Activity: ActivityIcon,
  More: MoreHorizontal,
};
function Workspace({
  api,
  logout,
}: {
  api: ApiClient;
  logout: () => Promise<void>;
}) {
  const readPage = () =>
    navigation.find((n) => n.toLowerCase() === location.hash.slice(1)) ??
    "Home";
  const [page, setPage] = useState<Page>(readPage);
  const data = useWorkspace(api);
  const reports = data.reports.data ?? [];
  const portfolios = data.portfolios.data ?? [];
  const jobs = data.jobs.data ?? [];
  useEffect(() => {
    const change = () => setPage(readPage());
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  function navigate(p: Page) {
    setPage(p);
    location.hash = p.toLowerCase();
    window.scrollTo({ top: 0 });
  }
  return (
    <div className="app-shell">
      <a className="skip" href="#content">
        Skip to content
      </a>
      <aside className="sidebar">
        <a className="brand" href="#home">
          <BarChart3 />
          Stock Scanner
        </a>
        <nav aria-label="Main navigation">
          {navigation.map((n) => {
            const Icon = icons[n];
            return (
              <button
                key={n}
                className={page === n ? "current" : ""}
                aria-current={page === n ? "page" : undefined}
                onClick={() => navigate(n)}
              >
                <Icon size={22} />
                <span>{n}</span>
              </button>
            );
          })}
        </nav>
        <div className="sidebar-footer">
          <Server size={16} />
          Private server
          <button aria-label="Disconnect" onClick={() => void logout()}>
            <LogOut size={18} />
          </button>
        </div>
      </aside>
      <div className="main">
        <header className="topbar">
          <h1>
            {page === "Research"
              ? "Market workspace"
              : page === "More"
                ? "Operations"
                : page}
          </h1>
          <span className="muted">
            {data.context.data?.latest_session ?? "Date unavailable"} · Market
            close data
          </span>
          <button
            className="mobile-logout"
            onClick={() => void logout()}
            aria-label="Disconnect"
          >
            <LogOut size={18} />
          </button>
        </header>
        <main id="content" className="content">
          <ErrorBox
            error={
              data.reports.error ??
              data.portfolios.error ??
              data.jobs.error ??
              data.context.error
            }
          />
          {page === "Home" ? (
            <Home
              api={api}
              reports={reports}
              jobs={jobs}
              latest={data.context.data?.latest_session}
              onResearch={() => navigate("Research")}
            />
          ) : page === "Research" ? (
            <Research
              api={api}
              reports={reports}
              portfolios={portfolios}
              latest={data.context.data?.latest_session}
            />
          ) : page === "Portfolio" ? (
            <Portfolio api={api} portfolios={portfolios} />
          ) : page === "Activity" ? (
            <Activity api={api} jobs={jobs} />
          ) : (
            <Operations api={api} portfolios={portfolios} reports={reports} />
          )}
        </main>
      </div>
    </div>
  );
}
