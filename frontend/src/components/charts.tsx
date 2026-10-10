import { useEffect, useMemo, useRef } from "react";
import {
  AreaSeries,
  CandlestickSeries,
  ColorType,
  CrosshairMode,
  HistogramSeries,
  LineStyle,
  createChart,
  type IChartApi,
  type IPriceLine,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";
import { useTheme } from "../context/theme";
import type { Candle } from "../lib/types";
import { cssVar } from "../lib/utils";
import { fmtCompact, fmtPct } from "../lib/format";

function palette() {
  return {
    bg: cssVar("--surface"),
    text: cssVar("--muted"),
    grid: cssVar("--border"),
    up: cssVar("--up"),
    down: cssVar("--down"),
    primary: cssVar("--primary"),
    info: cssVar("--info"),
  };
}

function precisionFor(price: number) {
  const a = Math.abs(price);
  if (a >= 1000) return 2;
  if (a >= 1) return 4;
  if (a >= 0.01) return 5;
  if (a === 0) return 2;
  return Math.min(10, -Math.floor(Math.log10(a)) + 3);
}

function baseOptions(p: ReturnType<typeof palette>) {
  return {
    layout: {
      background: { type: ColorType.Solid, color: p.bg },
      textColor: p.text,
      fontFamily: "Inter, Cairo, system-ui, sans-serif",
      fontSize: 11,
      attributionLogo: true, // TradingView attribution (Lightweight Charts license notice)
    },
    grid: { vertLines: { color: p.grid + "66" }, horzLines: { color: p.grid + "66" } },
    rightPriceScale: { borderColor: p.grid },
    timeScale: { borderColor: p.grid, timeVisible: true, secondsVisible: false },
    crosshair: { mode: CrosshairMode.Normal },
    autoSize: true,
  };
}

export interface PriceLineSpec {
  price: number;
  title: string;
  tone: "up" | "down" | "primary" | "info";
}

export function PriceChart({ candles, lines = [], height = 420, showVolume = true }: { candles: Candle[]; lines?: PriceLineSpec[]; height?: number; showVolume?: boolean }) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const candleSeries = useRef<ISeriesApi<"Candlestick"> | null>(null);
  const volSeries = useRef<ISeriesApi<"Histogram"> | null>(null);
  const priceLines = useRef<IPriceLine[]>([]);
  const fitted = useRef(false);
  const { resolved } = useTheme();

  useEffect(() => {
    if (!box.current) return;
    const p = palette();
    const c = createChart(box.current, baseOptions(p));
    candleSeries.current = c.addSeries(CandlestickSeries, {
      upColor: p.up, downColor: p.down, borderVisible: false, wickUpColor: p.up, wickDownColor: p.down,
    });
    candleSeries.current.priceScale().applyOptions({ scaleMargins: { top: 0.08, bottom: showVolume ? 0.24 : 0.06 } });
    if (showVolume) {
      volSeries.current = c.addSeries(HistogramSeries, { priceFormat: { type: "volume" }, priceScaleId: "" });
      volSeries.current.priceScale().applyOptions({ scaleMargins: { top: 0.8, bottom: 0 } });
    }
    chart.current = c;
    fitted.current = false;
    return () => {
      c.remove();
      chart.current = null;
      candleSeries.current = null;
      volSeries.current = null;
      priceLines.current = [];
    };
  }, [showVolume]);

  // Re-theme without rebuilding the chart.
  useEffect(() => {
    const p = palette();
    chart.current?.applyOptions(baseOptions(p));
    candleSeries.current?.applyOptions({ upColor: p.up, downColor: p.down, wickUpColor: p.up, wickDownColor: p.down });
  }, [resolved]);

  useEffect(() => {
    const s = candleSeries.current;
    if (!s || !candles.length) return;
    const p = palette();
    const last = candles[candles.length - 1][4];
    const precision = precisionFor(last);
    s.applyOptions({ priceFormat: { type: "price", precision, minMove: 1 / 10 ** precision } });
    s.setData(candles.map(([t, o, h, l, c]) => ({ time: Math.floor(t / 1000) as UTCTimestamp, open: o, high: h, low: l, close: c })));
    volSeries.current?.setData(
      candles.map(([t, o, , , c, v]) => ({ time: Math.floor(t / 1000) as UTCTimestamp, value: v, color: (c >= o ? p.up : p.down) + "55" })),
    );
    if (!fitted.current) {
      chart.current?.timeScale().fitContent();
      fitted.current = true;
    }
  }, [candles]);

  useEffect(() => {
    const s = candleSeries.current;
    if (!s) return;
    const p = palette();
    priceLines.current.forEach((l) => s.removePriceLine(l));
    priceLines.current = lines
      .filter((l) => Number.isFinite(l.price) && l.price > 0)
      .map((l) =>
        s.createPriceLine({ price: l.price, color: p[l.tone], lineWidth: 1, lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: l.title }),
      );
  }, [lines, resolved]);

  return <div ref={box} dir="ltr" style={{ height }} className="w-full" />;
}

export function AreaChart({ points, height = 220, tone = "primary", valueFormat }: { points: { t: number; v: number }[]; height?: number; tone?: "primary" | "up" | "down" | "info"; valueFormat?: (v: number) => string }) {
  const box = useRef<HTMLDivElement>(null);
  const chart = useRef<IChartApi | null>(null);
  const series = useRef<ISeriesApi<"Area"> | null>(null);
  const { resolved } = useTheme();

  useEffect(() => {
    if (!box.current) return;
    const p = palette();
    const c = createChart(box.current, { ...baseOptions(p), rightPriceScale: { borderVisible: false }, timeScale: { borderVisible: false, timeVisible: true } });
    series.current = c.addSeries(AreaSeries, {
      lineColor: p[tone], topColor: p[tone] + "55", bottomColor: p[tone] + "05", lineWidth: 2,
      priceFormat: valueFormat ? { type: "custom", formatter: valueFormat, minMove: 0.01 } : undefined,
    });
    chart.current = c;
    return () => {
      c.remove();
      chart.current = null;
      series.current = null;
    };
  }, [tone, valueFormat]);

  useEffect(() => {
    const p = palette();
    chart.current?.applyOptions({ layout: baseOptions(p).layout, grid: baseOptions(p).grid });
    series.current?.applyOptions({ lineColor: p[tone], topColor: p[tone] + "55", bottomColor: p[tone] + "05" });
  }, [resolved, tone]);

  useEffect(() => {
    if (!series.current) return;
    // lightweight-charts requires strictly increasing unique times
    const seen = new Map<number, number>();
    for (const pt of points) seen.set(Math.floor(pt.t / 1000), pt.v);
    const data = [...seen.entries()].sort((a, b) => a[0] - b[0]).map(([time, value]) => ({ time: time as UTCTimestamp, value }));
    series.current.setData(data);
    chart.current?.timeScale().fitContent();
  }, [points]);

  return <div ref={box} dir="ltr" style={{ height }} className="w-full" />;
}

/* ------------------------------------------------------------------ SVG charts */

const DONUT_COLORS = ["#ff9a1f", "#5b9cff", "#22c55e", "#a78bfa", "#f2555a", "#14b8a6", "#eab308", "#ec4899", "#94a3b8"];

export function Donut({ items, size = 168, thickness = 22, center }: { items: { label: string; value: number }[]; size?: number; thickness?: number; center?: React.ReactNode }) {
  const total = items.reduce((s, i) => s + Math.max(0, i.value), 0);
  const r = (size - thickness) / 2;
  const circ = 2 * Math.PI * r;
  let offset = 0;
  const segs = items.map((it, idx) => {
    const frac = total ? Math.max(0, it.value) / total : 0;
    const seg = { color: DONUT_COLORS[idx % DONUT_COLORS.length], dash: frac * circ, offset, label: it.label, frac };
    offset += frac * circ;
    return seg;
  });
  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`} role="img" aria-label="Allocation">
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--surface-3)" strokeWidth={thickness} />
        {segs.map((s) =>
          s.frac > 0 ? (
            <circle
              key={s.label}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={s.color}
              strokeWidth={thickness}
              strokeDasharray={`${Math.max(0, s.dash - 1.5)} ${circ}`}
              strokeDashoffset={-s.offset}
              transform={`rotate(-90 ${size / 2} ${size / 2})`}
            >
              <title>
                {s.label} {fmtPct(s.frac * 100, 1, false)}
              </title>
            </circle>
          ) : null,
        )}
      </svg>
      {center && <div className="absolute inset-0 flex flex-col items-center justify-center text-center">{center}</div>}
    </div>
  );
}

export function donutColor(i: number) {
  return DONUT_COLORS[i % DONUT_COLORS.length];
}

export function Gauge({ value, size = 180, label }: { value: number; size?: number; label?: string }) {
  const v = Math.max(0, Math.min(100, value));
  const r = size / 2 - 14;
  const cx = size / 2;
  const cy = size / 2 + 4;
  const arc = (from: number, to: number) => {
    const a0 = Math.PI * (1 - from / 100);
    const a1 = Math.PI * (1 - to / 100);
    const x0 = cx + r * Math.cos(a0), y0 = cy - r * Math.sin(a0);
    const x1 = cx + r * Math.cos(a1), y1 = cy - r * Math.sin(a1);
    return `M ${x0} ${y0} A ${r} ${r} 0 0 1 ${x1} ${y1}`;
  };
  const angle = Math.PI * (1 - v / 100);
  const nx = cx + (r - 8) * Math.cos(angle);
  const ny = cy - (r - 8) * Math.sin(angle);
  const bands: [number, number, string][] = [[0, 25, "#f2555a"], [25, 45, "#fb923c"], [45, 55, "#eab308"], [55, 75, "#84cc16"], [75, 100, "#22c55e"]];
  return (
    <svg width={size} height={size / 2 + 24} viewBox={`0 0 ${size} ${size / 2 + 24}`} role="img" aria-label={`${label ?? "Index"}: ${v}`}>
      {bands.map(([a, b, c]) => (
        <path key={a} d={arc(a + 0.8, b - 0.8)} stroke={c} strokeWidth={12} fill="none" strokeLinecap="round" />
      ))}
      <line x1={cx} y1={cy} x2={nx} y2={ny} stroke="var(--text)" strokeWidth={3} strokeLinecap="round" />
      <circle cx={cx} cy={cy} r={5} fill="var(--text)" />
    </svg>
  );
}

export function Sparkline({ values, width = 96, height = 28, className }: { values: number[]; width?: number; height?: number; className?: string }) {
  const path = useMemo(() => {
    if (values.length < 2) return "";
    const min = Math.min(...values), max = Math.max(...values);
    const span = max - min || 1;
    return values
      .map((v, i) => `${i === 0 ? "M" : "L"} ${(i / (values.length - 1)) * width} ${height - 2 - ((v - min) / span) * (height - 4)}`)
      .join(" ");
  }, [values, width, height]);
  const up = values.length > 1 && values[values.length - 1] >= values[0];
  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className={className} aria-hidden>
      <path d={path} fill="none" stroke={up ? "var(--up)" : "var(--down)"} strokeWidth={1.5} strokeLinejoin="round" />
    </svg>
  );
}

export function Bars({ items, height = 160, format = (v: number) => fmtCompact(v) }: { items: { label: string; value: number }[]; height?: number; format?: (v: number) => string }) {
  const max = Math.max(1, ...items.map((i) => Math.abs(i.value)));
  return (
    <div className="flex items-end gap-1.5" style={{ height }} dir="ltr">
      {items.map((it) => (
        <div key={it.label} className="flex min-w-0 flex-1 flex-col items-center justify-end gap-1" title={`${it.label}: ${format(it.value)}`}>
          <div className={it.value >= 0 ? "w-full rounded-t bg-primary/80" : "w-full rounded-t bg-down/80"} style={{ height: `${(Math.abs(it.value) / max) * (height - 22)}px` }} />
          <span className="w-full truncate text-center text-[10px] text-muted">{it.label}</span>
        </div>
      ))}
    </div>
  );
}
