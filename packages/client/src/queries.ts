import { useQuery } from "@tanstack/react-query";
import { ApiClient, Period, Scope, terminalStatuses } from "./index";

export function useWorkspace(api: ApiClient) {
  const reports = useQuery({
    queryKey: ["reports"],
    queryFn: () => api.reports(),
    staleTime: 30000,
  });
  const portfolios = useQuery({
    queryKey: ["portfolios"],
    queryFn: () => api.portfolios(),
  });
  const jobs = useQuery({
    queryKey: ["jobs"],
    queryFn: () => api.jobs(),
    refetchInterval: (q) =>
      q.state.data?.some((j) => !terminalStatuses.has(j.status)) ? 5000 : 30000,
  });
  const context = useQuery({
    queryKey: ["market-context"],
    queryFn: () => api.request<{ latest_session: string }>("/market/context"),
    staleTime: 60000,
  });
  return { reports, portfolios, jobs, context };
}
export function useMovement(
  api: ApiClient,
  scope: Scope,
  period: Period,
  reportId?: string,
  portfolioId?: string,
  date?: string,
) {
  return useQuery({
    queryKey: ["movement", scope, period, reportId, portfolioId, date],
    queryFn: () =>
      api.movement({
        scope,
        period,
        report_id: reportId,
        portfolio_id: portfolioId,
        data_date: date,
      }),
    enabled: !!date && (scope === "portfolio" ? !!portfolioId : !!reportId),
    staleTime: 60000,
  });
}
export function useBars(api: ApiClient, symbol?: string, date?: string) {
  return useQuery({
    queryKey: ["bars", symbol, date],
    queryFn: () => api.bars(symbol!, date),
    enabled: !!symbol && !!date,
    staleTime: 60000,
  });
}
