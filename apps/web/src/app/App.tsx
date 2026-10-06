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
} from "lucide-react";
import { ApiClient } from "@stock-scanner/client";
import { useWorkspace } from "@stock-scanner/client/queries";
import { navigation, Page } from "@stock-scanner/design";
import { BowlMark, KitchenScene } from "../components/Kitchen";
import { ThemeControls } from "../components/Theme";
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
        <div className="connecting">
          <BowlMark />
          <p>Warming up the kitchen…</p>
        </div>
      </div>
    );
  if (!connected)
    return (
      <main className="connect-shell">
        <div className="connect-preferences">
          <ThemeControls />
        </div>
        <div className="connect-layout">
          <div className="connect-story">
            <p className="eyebrow">WELCOME TO THE KITCHEN</p>
            <h2>
              A little clarity.
              <br />
              <em>A calmer market.</em>
            </h2>
            <KitchenScene />
          </div>
          <div className="connect-card">
            <BowlMark />
            <p className="eyebrow">YOUR PRIVATE CORNER</p>
            <h1>Come on in.</h1>
            <p className="muted">
              Your market research, portfolio and history in one quiet
              workspace.
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
    location.hash === "#settings"
      ? "More"
      : (navigation.find((n) => n.toLowerCase() === location.hash.slice(1)) ??
        "Home");
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
      <header className="site-header">
        <a className="brand" href="#home" onClick={() => navigate("Home")}>
          <BowlMark />
          <span>
            CoSoup<small>research, simmered</small>
          </span>
        </a>
        <nav className="main-nav" aria-label="Main navigation">
          {navigation.map((n) => {
            const Icon = icons[n];
            return (
              <button
                key={n}
                className={page === n ? "current" : ""}
                aria-current={page === n ? "page" : undefined}
                onClick={() => navigate(n)}
              >
                <Icon size={18} />
                <span>{n === "More" ? "Settings" : n}</span>
              </button>
            );
          })}
        </nav>
        <div className="header-actions">
          <ThemeControls />
          <button
            className="icon-button"
            aria-label="Disconnect"
            title="Leave your private kitchen"
            onClick={() => void logout()}
          >
            <LogOut size={18} />
          </button>
        </div>
      </header>
      <div className="main">
        <div className="page-heading">
          <h1>
            {page === "Research"
              ? "Market workspace"
              : page === "More"
                ? "Settings"
                : page}
          </h1>
          <span className="session-note">
            <span className="status-dot" aria-hidden="true" />
            {data.context.data?.latest_session ?? "Date unavailable"} · Market
            close data
          </span>
        </div>
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
              reportsReady={!data.reports.isPending}
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
            <Activity api={api} jobs={jobs} reports={reports} />
          ) : (
            <Operations api={api} portfolios={portfolios} reports={reports} />
          )}
        </main>
      </div>
    </div>
  );
}
