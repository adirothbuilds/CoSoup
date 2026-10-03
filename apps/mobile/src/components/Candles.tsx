import { useState } from "react";
import { View, Text, useWindowDimensions } from "react-native";
import Svg, { Line, Rect, Polyline, Text as SvgText } from "react-native-svg";
import { Bars, money, chartWindow } from "@stock-scanner/client";
import { colors } from "@stock-scanner/design";
import { styles, Toggle } from "./UI";
export default function Candles({
  data,
  pivot,
}: {
  data: Bars;
  pivot?: number;
}) {
  const [range, setRange] = useState<"1M" | "3M" | "1Y">("1M");
  const [selected, setSelected] = useState<Bars["bars"][number]>();
  const width = Math.min(useWindowDimensions().width - 64, 750);
  const window = chartWindow(data, range);
  const bars = window.bars;
  if (!bars.length)
    return <Text style={styles.muted}>No valid bars in this window.</Text>;
  const overlayValues = [...data.indicators.sma50, ...data.indicators.sma200]
    .filter((v) => window.sessions.includes(v.session))
    .map((v) => v.value);
  const low = Math.min(
      ...bars.map((b) => b.low),
      ...overlayValues,
      pivot ?? Infinity,
    ),
    high = Math.max(
      ...bars.map((b) => b.high),
      ...overlayValues,
      pivot ?? -Infinity,
    );
  const span = Math.max(high - low, 0.01);
  const y = (price: number) => 20 + ((high - price) / span) * 210;
  const step = (width - 46) / window.sessions.length;
  const maxVolume = Math.max(1, ...bars.map((b) => b.volume));
  const bar = selected ?? bars.at(-1)!;
  return (
    <View style={{ gap: 12 }}>
      <Toggle values={["1M", "3M", "1Y"]} value={range} onChange={setRange} />
      <Svg
        width={width}
        height={310}
        accessibilityLabel="Daily OHLC candles and volume. Tap a candle to read its values."
      >
        {[0, 1, 2, 3, 4].map((i) => (
          <Line
            key={i}
            x1={0}
            x2={width - 38}
            y1={20 + i * 52.5}
            y2={20 + i * 52.5}
            stroke={colors.border}
          />
        ))}
        {pivot && (
          <>
            <Line
              x1={0}
              x2={width - 38}
              y1={y(pivot)}
              y2={y(pivot)}
              stroke={colors.muted}
              strokeDasharray="4 4"
            />
            <SvgText x={4} y={y(pivot) - 5} fill={colors.muted} fontSize={10}>
              Breakout {money(pivot)}
            </SvgText>
          </>
        )}
        {bars.map((b, i) => {
          const index = window.sessions.indexOf(b.session);
          const x = index * step + step / 2;
          const color = b.close >= b.open ? colors.positive : colors.negative;
          return (
            <ViewPlaceholder key={b.session}>
              {
                <>
                  <Line
                    x1={x}
                    x2={x}
                    y1={y(b.high)}
                    y2={y(b.low)}
                    stroke={color}
                  />
                  <Rect
                    x={x - Math.max(1, step * 0.28)}
                    y={Math.min(y(b.open), y(b.close))}
                    width={Math.max(1, step * 0.56)}
                    height={Math.max(1, Math.abs(y(b.open) - y(b.close)))}
                    fill={color}
                  />
                  <Rect
                    x={x - Math.max(1, step * 0.28)}
                    y={285 - (b.volume / maxVolume) * 45}
                    width={Math.max(1, step * 0.56)}
                    height={(b.volume / maxVolume) * 45}
                    fill={color}
                    opacity={0.5}
                  />
                  <Rect
                    x={index * step}
                    y={0}
                    width={Math.max(step, 1)}
                    height={290}
                    fill="transparent"
                    onPress={() => setSelected(b)}
                    accessibilityLabel={`${b.session}, open ${b.open}, high ${b.high}, low ${b.low}, close ${b.close}, volume ${b.volume}`}
                  />
                </>
              }
            </ViewPlaceholder>
          );
        })}
        {(["sma50", "sma200"] as const).map((key, i) => {
          const points = data.indicators[key]
            .filter((v) => bars.some((b) => b.session === v.session))
            .map(
              (v) =>
                `${window.sessions.indexOf(v.session) * step + step / 2},${y(v.value)}`,
            )
            .join(" ");
          return (
            <Polyline
              key={key}
              points={points}
              fill="none"
              stroke={i ? "#ad9ccc" : colors.accent}
              strokeWidth={1}
            />
          );
        })}
        <SvgText x={width - 35} y={24} fill={colors.muted} fontSize={9}>
          {high.toFixed(2)}
        </SvgText>
        <SvgText x={width - 35} y={232} fill={colors.muted} fontSize={9}>
          {low.toFixed(2)}
        </SvgText>
        <SvgText x={0} y={307} fill={colors.muted} fontSize={9}>
          {bars[0].session}
        </SvgText>
        <SvgText x={width - 120} y={307} fill={colors.muted} fontSize={9}>
          {bars.at(-1)!.session}
        </SvgText>
      </Svg>
      <Text style={styles.muted}>
        {bar.session} · O {money(bar.open)} · H {money(bar.high)} · L{" "}
        {money(bar.low)} · C {money(bar.close)} · Vol{" "}
        {bar.volume.toLocaleString()}
      </Text>
      <Text style={styles.muted}>
        Daily sessions · SMA50 / SMA200 · Split-adjusted through{" "}
        {data.adjustment_cutoff}
      </Text>
      {!!data.missing_sessions.length && (
        <Text style={[styles.muted, { color: colors.warning }]}>
          {data.missing_sessions.length} missing/invalid cached sessions. No
          synthetic candles.
        </Text>
      )}
    </View>
  );
}
// A fragment keeps SVG children native without introducing a DOM wrapper.
function ViewPlaceholder({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}
