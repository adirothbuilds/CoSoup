import { useState } from "react";
import { Disclosure } from "../../components/UI";
export type ChatChart = {
  id: string;
  source_id: string;
  title: string;
  kind: "line" | "bar";
  unit: string;
  note: string;
  points: { label: string; value: number }[];
};
export default function ChatCharts({ charts }: { charts: ChatChart[] }) {
  const [hover, setHover] = useState<Record<string, number>>({});
  return (
    <div className="chat-charts">
      {charts.map((c, n) => {
        const baseline = c.kind === "bar" ? [0] : [],
          max = Math.max(...c.points.map((p) => p.value), ...baseline),
          min = Math.min(...c.points.map((p) => p.value), ...baseline),
          range = max - min || 1;
        const x = (i: number) =>
            35 + (i * 490) / Math.max(1, c.points.length - 1),
          y = (v: number) => 170 - ((v - min) * 145) / range;
        const selected = c.points[hover[c.id] ?? c.points.length - 1];
        return (
          <figure className="chat-chart" key={`${c.id}-${n}`}>
            <figcaption>
              <strong>{c.title}</strong>
              <small>{c.unit}</small>
            </figcaption>
            {c.kind === "line" && c.points.length > 1 ? (
              <>
                <div className="chart-readout">
                  {selected?.label}{" "}
                  <strong>
                    {selected?.value.toLocaleString(undefined, {
                      maximumFractionDigits: 2,
                    })}{" "}
                    {c.unit}
                  </strong>
                </div>
                <svg viewBox="0 0 560 200" role="img" aria-label={c.title}>
                  {[min, max].map((v, i) => (
                    <g key={i}>
                      <line
                        x1="35"
                        x2="525"
                        y1={y(v)}
                        y2={y(v)}
                        className="plot-grid"
                      />
                      <text x="35" y={y(v) - 5}>
                        {v.toLocaleString(undefined, {
                          maximumFractionDigits: 1,
                        })}
                      </text>
                    </g>
                  ))}
                  <polyline
                    points={c.points
                      .map((p, i) => `${x(i)},${y(p.value)}`)
                      .join(" ")}
                    fill="none"
                    className="plot-line"
                  />
                  {c.points.map((p, i) => (
                    <circle
                      key={i}
                      cx={x(i)}
                      cy={y(p.value)}
                      r="6"
                      className="plot-point"
                      onMouseEnter={() => setHover({ ...hover, [c.id]: i })}
                      onClick={() => setHover({ ...hover, [c.id]: i })}
                    >
                      <title>
                        {p.label}: {p.value} {c.unit}
                      </title>
                    </circle>
                  ))}
                  <text x="35" y="195">
                    {c.points[0]?.label}
                  </text>
                  <text x="525" y="195" textAnchor="end">
                    {c.points.at(-1)?.label}
                  </text>
                </svg>
              </>
            ) : (
              <div className="chat-bar-chart">
                {c.points.map((p, i) => (
                  <div key={i}>
                    <span>{p.label}</span>
                    <div className="plot-bar-track">
                      <div
                        style={{
                          width: `${Math.max(1, (Math.abs(p.value) / Math.max(Math.abs(min), max, 1)) * 100)}%`,
                        }}
                        className={p.value < 0 ? "negative" : ""}
                      />
                    </div>
                    <strong>
                      {p.value.toLocaleString(undefined, {
                        maximumFractionDigits: 2,
                      })}
                    </strong>
                  </div>
                ))}
              </div>
            )}
            <p className="muted small">{c.note}</p>
            <Disclosure title="Chart values & source">
              <a
                href={
                  c.id.endsWith(":basis")
                    ? "#portfolio"
                    : `?report=${encodeURIComponent(c.source_id)}#home`
                }
              >
                {c.id.endsWith(":basis")
                  ? "Open portfolio journal"
                  : "Open dated evidence"}
              </a>
              <div className="table-scroll">
                <table>
                  <thead>
                    <tr>
                      <th>Observation</th>
                      <th>{c.unit || "Value"}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.points.map((p, i) => (
                      <tr key={i}>
                        <td>{p.label}</td>
                        <td>{p.value}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Disclosure>
          </figure>
        );
      })}
    </div>
  );
}
