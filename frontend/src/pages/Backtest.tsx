import { useMemo, useState } from "react";
import { useSearchParams } from "react-router";
import { useMutation } from "@tanstack/react-query";
import { FlaskConical, Play, Sparkles } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import { useMarketExchange } from "../lib/hooks";
import type { BacktestResult, OptimizeResult } from "../lib/types";
import { fmtDateTime, fmtNum, fmtPct, fmtPrice, fmtUsd, slugToSymbol, trendClass } from "../lib/format";
import { cn, toNumber } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Field, Input, Notice, PageHeader, Segmented, Select, Stat, Table, Tabs, Td, Th } from "../components/ui";
import { AreaChart } from "../components/charts";
import { SymbolPicker } from "../components/market";

const PARAMS = {
  take_profit: { label: "Take profit %", min: 0.5, max: 3, step: 0.5 },
  deviation: { label: "SO deviation %", min: 0.5, max: 3, step: 0.5 },
  max_safety_orders: { label: "Max safety orders", min: 0, max: 8, step: 2 },
  volume_scale: { label: "Volume scale", min: 1, max: 2, step: 0.25 },
  step_scale: { label: "Step scale", min: 1, max: 1.6, step: 0.2 },
  stop_loss: { label: "Stop loss %", min: 0, max: 10, step: 2.5 },
} as const;
type ParamKey = keyof typeof PARAMS;

const usd = (v: number) => fmtUsd(v);

export default function Backtest() {
  const t = useT();
  const toast = useToast();
  const exchange = useMarketExchange();
  const [params] = useSearchParams();
  const [tab, setTab] = useState<"run" | "optimize">("run");
  const [f, setF] = useState({
    symbol: slugToSymbol(params.get("symbol") ?? "BTC-USDT"),
    timeframe: "1h", limit: "720", strategy: "long", base_order: "100", safety_order: "100", max_safety_orders: "5",
    deviation: "1.5", step_scale: "1.1", volume_scale: "1.4", take_profit: "1.5", stop_loss: "0", fee: "0.1", rsi_below: "0",
  });
  const set = (k: keyof typeof f) => (v: string) => setF((s) => ({ ...s, [k]: v }));
  const body = () => ({
    exchange, symbol: f.symbol, timeframe: f.timeframe, limit: toNumber(f.limit, 500), strategy: f.strategy,
    base_order: toNumber(f.base_order), safety_order: toNumber(f.safety_order), max_safety_orders: toNumber(f.max_safety_orders),
    deviation: toNumber(f.deviation), step_scale: toNumber(f.step_scale, 1), volume_scale: toNumber(f.volume_scale, 1),
    take_profit: toNumber(f.take_profit), stop_loss: toNumber(f.stop_loss), fee: toNumber(f.fee), rsi_below: toNumber(f.rsi_below),
  });

  const run = useMutation({ mutationFn: () => v2.post<BacktestResult>("/backtest", body()), onError: (e) => toast.error(e) });

  const [axes, setAxes] = useState<ParamKey[]>(["take_profit", "deviation"]);
  const [ranges, setRanges] = useState<Record<ParamKey, { min: string; max: string; step: string }>>(
    Object.fromEntries(Object.entries(PARAMS).map(([k, v]) => [k, { min: String(v.min), max: String(v.max), step: String(v.step) }])) as Record<ParamKey, { min: string; max: string; step: string }>,
  );
  const [metric, setMetric] = useState("return_pct");
  const combos = axes.reduce((n, k) => n * (Math.floor((toNumber(ranges[k].max) - toNumber(ranges[k].min)) / (toNumber(ranges[k].step) || 1)) + 1), 1);
  const optimize = useMutation({
    mutationFn: () =>
      v2.post<OptimizeResult>("/backtest/optimize", {
        ...body(), metric,
        grid: Object.fromEntries(axes.map((k) => [k, { min: toNumber(ranges[k].min), max: toNumber(ranges[k].max), step: toNumber(ranges[k].step) || 1 }])),
      }),
    onError: (e) => toast.error(e),
  });

  const r = run.data;
  const equity = useMemo(() => (r?.equity ?? []).map((p) => ({ t: p.t, v: p.equity })), [r]);
  const applyBest = (p: Record<string, number>) => {
    setF((s) => ({ ...s, ...Object.fromEntries(Object.entries(p).map(([k, v]) => [k, String(v)])) }));
    setTab("run");
    toast.info(t("bt.applied", "Best parameters applied — run the backtest to see the details."));
  };

  return (
    <div className="space-y-5">
      <PageHeader icon={<FlaskConical className="size-5" />} title={t("nav.backtest", "Backtest")} subtitle={t("bt.subtitle", "Replay the DCA bot strategy on historical candles before risking real money.")} />
      <div className="grid gap-5 xl:grid-cols-[360px_1fr]">
        <Card className="self-start">
          <CardHeader title={t("bt.strategy", "Strategy")} />
          <CardBody className="space-y-4">
            <Field label={t("market.pair", "Pair")}><SymbolPicker value={f.symbol} onChange={set("symbol")} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("bt.timeframe", "Timeframe")}>
                <Select value={f.timeframe} onChange={(e) => set("timeframe")(e.target.value)}>
                  {["15m", "1h", "4h", "1d"].map((v) => <option key={v} value={v}>{v}</option>)}
                </Select>
              </Field>
              <Field label={t("bt.candles", "Candles")}><Input inputMode="numeric" value={f.limit} onChange={(e) => set("limit")(e.target.value)} /></Field>
            </div>
            <Segmented value={f.strategy} onChange={set("strategy")} className="w-full" options={[{ value: "long", label: t("bots.long", "Long"), tone: "up" }, { value: "short", label: t("bots.short", "Short"), tone: "down" }]} />
            <div className="grid grid-cols-2 gap-3">
              <Field label={t("bt.base", "Base order")}><Input inputMode="decimal" value={f.base_order} onChange={(e) => set("base_order")(e.target.value)} suffix="$" /></Field>
              <Field label={t("bt.so", "Safety order")}><Input inputMode="decimal" value={f.safety_order} onChange={(e) => set("safety_order")(e.target.value)} suffix="$" /></Field>
              <Field label={t("bots.so_count", "Max safety orders")}><Input inputMode="numeric" value={f.max_safety_orders} onChange={(e) => set("max_safety_orders")(e.target.value)} /></Field>
              <Field label={t("bots.so_dev", "Price deviation")}><Input inputMode="decimal" value={f.deviation} onChange={(e) => set("deviation")(e.target.value)} suffix="%" /></Field>
              <Field label={t("bots.so_step", "Step scale")}><Input inputMode="decimal" value={f.step_scale} onChange={(e) => set("step_scale")(e.target.value)} suffix="×" /></Field>
              <Field label={t("bots.so_volume", "Volume scale")}><Input inputMode="decimal" value={f.volume_scale} onChange={(e) => set("volume_scale")(e.target.value)} suffix="×" /></Field>
              <Field label={t("bots.tp_target", "Target profit")}><Input inputMode="decimal" value={f.take_profit} onChange={(e) => set("take_profit")(e.target.value)} suffix="%" /></Field>
              <Field label={t("bots.stop_loss", "Stop loss")} hint={t("bt.zero_off", "0 = off")}><Input inputMode="decimal" value={f.stop_loss} onChange={(e) => set("stop_loss")(e.target.value)} suffix="%" /></Field>
              <Field label={t("bt.fee", "Fee per order")}><Input inputMode="decimal" value={f.fee} onChange={(e) => set("fee")(e.target.value)} suffix="%" /></Field>
              <Field label={t("bt.rsi", "Enter when RSI <")} hint={t("bt.zero_off", "0 = off")}><Input inputMode="decimal" value={f.rsi_below} onChange={(e) => set("rsi_below")(e.target.value)} /></Field>
            </div>
            <Button className="w-full" icon={<Play className="size-4" />} loading={run.isPending} onClick={() => { setTab("run"); run.mutate(); }}>{t("bt.run", "Run backtest")}</Button>
          </CardBody>
        </Card>

        <div className="min-w-0 space-y-5">
          <Tabs value={tab} onChange={setTab} tabs={[{ value: "run", label: t("bt.results", "Results") }, { value: "optimize", label: t("bt.optimize", "Optimize") }]} />
          {tab === "run" && (
            !r ? (
              <Card><EmptyState icon={<FlaskConical className="size-6" />} title={t("bt.empty", "Configure a strategy and run the backtest")} body={t("bt.empty_b", "Results include every simulated deal, an equity curve and risk statistics.")} /></Card>
            ) : (
              <>
                {r.source === "synthetic" && <Notice>{t("bt.synthetic", "Live market data was unavailable, so this run used the built-in demo market.")}</Notice>}
                <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                  <Card className="p-4"><Stat label={t("bt.return", "Return on capital")} value={fmtPct(r.stats.return_pct)} tone={trendClass(r.stats.return_pct)} hint={`${t("bt.hold", "Buy & hold")} ${fmtPct(r.stats.buy_and_hold_pct)}`} /></Card>
                  <Card className="p-4"><Stat label={t("bt.pnl", "Realized P&L")} value={fmtUsd(r.stats.realized_pnl)} tone={trendClass(r.stats.realized_pnl)} hint={`${t("bt.capital", "Capital")} ${fmtUsd(r.stats.max_capital, 0)}`} /></Card>
                  <Card className="p-4"><Stat label={t("bt.winrate", "Win rate")} value={fmtPct(r.stats.win_rate, 1, false)} hint={`${r.stats.wins}/${r.stats.deals} ${t("bt.deals", "deals")}`} /></Card>
                  <Card className="p-4"><Stat label={t("bt.mdd", "Max drawdown")} value={fmtPct(-r.stats.max_drawdown_pct)} tone="text-down" hint={`Calmar ${fmtNum(r.stats.calmar)}`} /></Card>
                  <Card className="p-4"><Stat label={t("bt.pf", "Profit factor")} value={r.stats.profit_factor === null ? "∞" : fmtNum(r.stats.profit_factor)} /></Card>
                  <Card className="p-4"><Stat label={t("bt.expectancy", "Avg P&L per deal")} value={fmtUsd(r.stats.expectancy)} tone={trendClass(r.stats.expectancy)} /></Card>
                  <Card className="p-4"><Stat label={t("bt.duration", "Avg deal length")} value={`${fmtNum(r.stats.avg_duration_h, 1)} h`} hint={`${fmtNum(r.stats.avg_safety_orders, 1)} ${t("bt.avg_so", "SOs on average")}`} /></Card>
                  <Card className="p-4"><Stat label={t("bt.exposure", "Time in market")} value={fmtPct(r.stats.exposure_pct, 1, false)} hint={`${r.stats.candles} ${t("bt.candles_l", "candles")}`} /></Card>
                </div>
                <Card>
                  <CardHeader title={t("bt.equity", "Equity curve")} subtitle={`${fmtDateTime(r.stats.from)} → ${fmtDateTime(r.stats.to)}`} />
                  <CardBody className="pt-2"><AreaChart points={equity} height={260} tone={r.stats.realized_pnl >= 0 ? "up" : "down"} valueFormat={usd} /></CardBody>
                </Card>
                {r.open_deal && <Notice tone="warning">{t("bt.open_deal", "A deal was still open at the end: {n} safety orders, unrealized {p}.", { n: r.open_deal.safety_orders, p: fmtUsd(r.open_deal.unrealized) })}</Notice>}
                <Card>
                  <CardHeader title={t("bt.deal_list", "Deals")} subtitle={t("bt.last_n", "Last {n}", { n: r.deals.length })} />
                  <Table>
                    <thead>
                      <tr>
                        <Th>{t("bt.opened", "Opened")}</Th><Th>{t("bt.closed", "Closed")}</Th><Th align="end">{t("bt.entry", "Entry")}</Th><Th align="end">{t("bots.avg", "Avg")}</Th>
                        <Th align="end">{t("bt.exit", "Exit")}</Th><Th align="end">SO</Th><Th align="end">P&L</Th><Th>{t("bt.reason", "Exit reason")}</Th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...r.deals].reverse().map((d, i) => (
                        <tr key={i}>
                          <Td className="text-muted">{fmtDateTime(d.open_time)}</Td>
                          <Td className="text-muted">{fmtDateTime(d.close_time)}</Td>
                          <Td align="end" className="num">{fmtPrice(d.entry)}</Td>
                          <Td align="end" className="num">{fmtPrice(d.average)}</Td>
                          <Td align="end" className="num">{fmtPrice(d.exit)}</Td>
                          <Td align="end" className="num">{d.safety_orders}</Td>
                          <Td align="end" className={cn("num", trendClass(d.pnl))}>{fmtUsd(d.pnl)} <span className="text-xs">({fmtPct(d.pnl_pct)})</span></Td>
                          <Td><Badge tone={d.reason === "take_profit" ? "up" : "down"}>{d.reason === "take_profit" ? t("bt.tp", "Take profit") : t("bt.sl", "Stop loss")}</Badge></Td>
                        </tr>
                      ))}
                    </tbody>
                  </Table>
                </Card>
              </>
            )
          )}

          {tab === "optimize" && (
            <>
              <Card>
                <CardHeader title={t("bt.grid", "Parameter grid")} subtitle={t("bt.grid_sub", "Up to 150 combinations are tested on the same candles.")} />
                <CardBody className="space-y-4">
                  {[0, 1].map((slot) => (
                    <div key={slot} className="grid grid-cols-2 gap-3 sm:grid-cols-4">
                      <Field label={slot === 0 ? t("bt.param_x", "Parameter 1") : t("bt.param_y", "Parameter 2 (optional)")}>
                        <Select
                          value={axes[slot] ?? ""}
                          onChange={(e) => {
                            const v = e.target.value as ParamKey | "";
                            const next = [...axes];
                            if (v) next[slot] = v;
                            else next.splice(slot, 1);
                            setAxes([...new Set(next)].filter(Boolean) as ParamKey[]);
                          }}
                        >
                          {slot === 1 && <option value="">—</option>}
                          {(Object.keys(PARAMS) as ParamKey[]).map((k) => <option key={k} value={k}>{t(`bt.p.${k}`, PARAMS[k].label)}</option>)}
                        </Select>
                      </Field>
                      {axes[slot] && (["min", "max", "step"] as const).map((b) => (
                        <Field key={b} label={b}>
                          <Input inputMode="decimal" value={ranges[axes[slot]][b]} onChange={(e) => setRanges({ ...ranges, [axes[slot]]: { ...ranges[axes[slot]], [b]: e.target.value } })} />
                        </Field>
                      ))}
                    </div>
                  ))}
                  <div className="flex flex-wrap items-end gap-3">
                    <Field label={t("bt.metric", "Rank by")}>
                      <Select value={metric} onChange={(e) => setMetric(e.target.value)}>
                        <option value="return_pct">{t("bt.return", "Return on capital")}</option>
                        <option value="profit_factor">{t("bt.pf", "Profit factor")}</option>
                        <option value="calmar">Calmar</option>
                        <option value="win_rate">{t("bt.winrate", "Win rate")}</option>
                        <option value="realized_pnl">{t("bt.pnl", "Realized P&L")}</option>
                      </Select>
                    </Field>
                    <span className={cn("num pb-2.5 text-sm", combos > 150 ? "text-down" : "text-muted")}>{t("bt.combos", "{n} combinations", { n: combos })}</span>
                    <Button className="ms-auto" icon={<Sparkles className="size-4" />} loading={optimize.isPending} disabled={combos > 150 || combos < 1} onClick={() => optimize.mutate()}>{t("bt.run_opt", "Optimize")}</Button>
                  </div>
                </CardBody>
              </Card>
              {optimize.data && (
                <>
                  {optimize.data.heatmap && <OptHeatmap data={optimize.data} />}
                  <Card>
                    <CardHeader title={t("bt.top", "Top results")} subtitle={t("bt.runs", "{n} runs on {c} candles", { n: optimize.data.runs, c: optimize.data.candles })} />
                    <Table>
                      <thead>
                        <tr>
                          {axes.map((k) => <Th key={k}>{t(`bt.p.${k}`, PARAMS[k].label)}</Th>)}
                          <Th align="end">{t("bt.return", "Return on capital")}</Th><Th align="end">{t("bt.winrate", "Win rate")}</Th>
                          <Th align="end">{t("bt.mdd", "Max drawdown")}</Th><Th align="end">{t("bt.deals", "deals")}</Th><Th align="end" />
                        </tr>
                      </thead>
                      <tbody>
                        {optimize.data.top.map((row, i) => (
                          <tr key={i} className={i === 0 ? "bg-primary-soft/40" : undefined}>
                            {axes.map((k) => <Td key={k} className="num">{row.params[k]}</Td>)}
                            <Td align="end" className={cn("num", trendClass(row.stats.return_pct))}>{fmtPct(row.stats.return_pct)}</Td>
                            <Td align="end" className="num">{fmtPct(row.stats.win_rate, 1, false)}</Td>
                            <Td align="end" className="num text-down">{fmtPct(-row.stats.max_drawdown_pct)}</Td>
                            <Td align="end" className="num">{row.stats.deals}</Td>
                            <Td align="end"><Button size="xs" variant="outline" onClick={() => applyBest(row.params)}>{t("bt.apply", "Apply")}</Button></Td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  </Card>
                </>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

function OptHeatmap({ data }: { data: OptimizeResult }) {
  const t = useT();
  const h = data.heatmap!;
  const scores = h.cells.map((c) => c[2]).filter((s) => s < 1e8);
  const lo = Math.min(...scores), hi = Math.max(...scores);
  const cell = (x: number, y: number) => h.cells.find((c) => c[0] === x && c[1] === y)?.[2];
  const color = (s?: number) => {
    if (s === undefined) return "transparent";
    if (s >= 1e8) return "rgb(34 197 94 / 0.9)";
    const p = hi === lo ? 0.5 : (s - lo) / (hi - lo);
    return s >= 0 ? `rgb(34 197 94 / ${0.15 + p * 0.75})` : `rgb(242 85 90 / ${0.15 + (1 - p) * 0.75})`;
  };
  return (
    <Card>
      <CardHeader title={t("bt.heatmap", "Heatmap")} subtitle={`${h.x} × ${h.y}`} />
      <CardBody className="overflow-x-auto">
        <table className="mx-auto text-xs" dir="ltr">
          <tbody>
            {[...h.ys].reverse().map((y) => (
              <tr key={y}>
                <th className="num pe-2 text-end font-normal text-muted">{y}</th>
                {h.xs.map((x) => {
                  const s = cell(x, y);
                  return (
                    <td key={x} className="p-0.5">
                      <div className="num flex h-9 w-14 items-center justify-center rounded text-[11px] text-fg" style={{ background: color(s) }} title={`${h.x}=${x} ${h.y}=${y}: ${s?.toFixed(2)}`}>
                        {s === undefined ? "" : s >= 1e8 ? "∞" : s.toFixed(1)}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
            <tr>
              <th />
              {h.xs.map((x) => <th key={x} className="num pt-1 font-normal text-muted">{x}</th>)}
            </tr>
          </tbody>
        </table>
      </CardBody>
    </Card>
  );
}
