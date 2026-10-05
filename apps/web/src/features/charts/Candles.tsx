import { useEffect, useRef, useState } from "react";
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  LineSeries,
  ColorType,
  Time,
} from "lightweight-charts";
import { Bars, chartWindow, money } from "@stock-scanner/client";
import { useTheme } from "../../components/Theme";
import { Toggle } from "../../components/UI";

export default function Candles({
  data,
  pivot,
}: {
  data: Bars;
  pivot?: number;
}) {
  const { colors, theme } = useTheme();
  const container = useRef<HTMLDivElement>(null);
  const [range, setRange] = useState<"1M" | "3M" | "1Y">("1M");
  const [averages, setAverages] = useState(true);
  const [readout, setReadout] = useState<Bars["bars"][number]>();
  const window = chartWindow(data, range);
  const shown = window.bars;
  const first = window.sessions[0];
  useEffect(() => {
    if (!container.current || !shown.length) return;
    const chart = createChart(container.current, {
      autoSize: true,
      height: 360,
      layout: {
        background: { type: ColorType.Solid, color: colors.panel },
        textColor: colors.muted,
        attributionLogo: true,
      },
      grid: {
        vertLines: { color: colors.border },
        horzLines: { color: colors.border },
      },
      rightPriceScale: { borderColor: colors.border },
      timeScale: { borderColor: colors.border, timeVisible: false },
      handleScroll: { vertTouchDrag: false },
    });
    const candles = chart.addSeries(CandlestickSeries, {
      upColor: colors.positive,
      downColor: colors.negative,
      wickUpColor: colors.positive,
      wickDownColor: colors.negative,
      borderVisible: false,
    });
    const entries = [
      ...shown.map((b) => ({
        time: b.session as Time,
        open: b.open,
        high: b.high,
        low: b.low,
        close: b.close,
      })),
      ...data.missing_sessions
        .filter(
          (m) => m.session >= (first ?? "") && m.session <= data.data_date,
        )
        .map((m) => ({ time: m.session as Time })),
    ].sort((a, b) => String(a.time).localeCompare(String(b.time)));
    candles.setData(entries);
    if (pivot)
      candles.createPriceLine({
        price: pivot,
        color: colors.muted,
        lineWidth: 1,
        lineStyle: 2,
        axisLabelVisible: true,
        title: "Breakout",
      });
    const volume = chart.addSeries(
      HistogramSeries,
      { priceFormat: { type: "volume" }, priceScaleId: "" },
      1,
    );
    volume.setData(
      shown.map((b) => ({
        time: b.session as Time,
        value: b.volume,
        color: b.close >= b.open ? colors.positive : colors.negative,
      })),
    );
    chart.panes()[1]?.setHeight(74);
    if (averages)
      for (const [key, color] of [
        ["sma50", colors.accent],
        ["sma200", theme === "light" ? "#866f9c" : "#c4a9de"],
      ] as const) {
        const line = chart.addSeries(LineSeries, {
          color,
          lineWidth: 1,
          lastValueVisible: false,
          priceLineVisible: false,
        });
        line.setData(
          data.indicators[key]
            .filter((i) => i.session >= (first ?? ""))
            .map((i) => ({ time: i.session as Time, value: i.value })),
        );
      }
    chart.subscribeCrosshairMove((p) => {
      if (p.time) setReadout(shown.find((b) => b.session === String(p.time)));
    });
    chart.timeScale().fitContent();
    return () => chart.remove();
  }, [data, range, averages, pivot, colors, theme]);
  const bar = readout ?? shown.at(-1);
  return (
    <div className="candles">
      <div className="chart-controls">
        <Toggle
          values={["1M", "3M", "1Y"]}
          value={range}
          onChange={setRange}
          label="Chart range"
        />
        <label className="check">
          <input
            type="checkbox"
            checked={averages}
            onChange={(e) => setAverages(e.target.checked)}
          />
          SMA50 / SMA200
        </label>
      </div>
      <div ref={container} className="chart" data-testid="daily-candles" />
      {bar && (
        <p className="chart-readout">
          {bar.session} · O {money(bar.open)} · H {money(bar.high)} · L{" "}
          {money(bar.low)} · C {money(bar.close)} · Vol{" "}
          {bar.volume.toLocaleString("en-US")}
        </p>
      )}
      <p className="muted small">
        One candle = one completed trading session · Split-adjusted through{" "}
        {data.adjustment_cutoff}
      </p>
      {data.missing_sessions.length > 0 && (
        <p className="warning">
          {data.missing_sessions.length} missing/invalid sessions in the cached
          window. Gaps are not filled.
        </p>
      )}
      <details>
        <summary>Accessible daily prices</summary>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Session</th>
                <th>Open</th>
                <th>High</th>
                <th>Low</th>
                <th>Close</th>
                <th>Volume</th>
              </tr>
            </thead>
            <tbody>
              {shown.map((b) => (
                <tr key={b.session}>
                  <td>{b.session}</td>
                  <td>{money(b.open)}</td>
                  <td>{money(b.high)}</td>
                  <td>{money(b.low)}</td>
                  <td>{money(b.close)}</td>
                  <td>{b.volume.toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </details>
    </div>
  );
}
