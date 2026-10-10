import { useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, Bot as BotIcon, Plug, Plus, RefreshCw, Target, Wallet } from "lucide-react";
import { useAuth } from "../context/auth";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import type { Bot, Insights, Portfolio, SmartTrade, Transaction } from "../lib/types";
import { fmtCompact, fmtDateTime, fmtPct, fmtUsd, trendClass } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, PageHeader, Segmented, Skeleton, Stat } from "../components/ui";
import { AreaChart, Donut, Gauge, donutColor } from "../components/charts";
import { BotRow, SmartTradeRow } from "../components/trading";
import { Change, Price, SymbolCell, useWatchlist } from "../components/market";

const usd = (v: number) => fmtUsd(v);

export function useInsights() {
  return useQuery({ queryKey: ["insights"], queryFn: () => v2.get<Insights>("/insights"), staleTime: 5 * 60_000 });
}

export function FearGreedCard({ data }: { data?: Insights }) {
  const t = useT();
  if (!data) return <Skeleton className="h-56" />;
  const fg = data.fear_greed;
  const attr = data.attribution[fg.source];
  const g = data.global;
  return (
    <Card>
      <CardHeader title={t("pulse.title", "Market pulse")} subtitle={g.source === "synthetic" ? t("pulse.demo", "Demo data") : undefined} />
      <CardBody className="grid gap-4 sm:grid-cols-[auto_1fr] sm:items-center">
        <div className="flex flex-col items-center">
          <Gauge value={fg.current.value} label={t("pulse.fng", "Fear & Greed")} />
          <p className="num -mt-2 text-2xl font-bold text-fg">{fg.current.value}</p>
          <p className="text-sm text-muted">{fg.current.classification}</p>
          {attr?.url && (
            <a href={attr.url} target="_blank" rel="noreferrer" className="mt-1 text-[11px] text-muted hover:text-fg">
              {t("pulse.source", "Source")}: {attr.name}
            </a>
          )}
        </div>
        <div className="grid grid-cols-2 gap-4">
          <Stat label={t("pulse.mcap", "Total market cap")} value={fmtCompact(g.total_market_cap_usd, "$")} hint={<span className={trendClass(g.market_cap_change_24h)}>{fmtPct(g.market_cap_change_24h)} 24h</span>} />
          <Stat label={t("pulse.volume", "24h volume")} value={fmtCompact(g.total_volume_usd, "$")} />
          <Stat label={t("pulse.btc_dom", "BTC dominance")} value={fmtPct(g.btc_dominance, 1, false)} />
          <Stat label={t("pulse.tvl", "DeFi TVL")} value={fmtCompact(data.defi.total_tvl, "$")} />
        </div>
      </CardBody>
    </Card>
  );
}

export default function Dashboard() {
  const t = useT();
  const { user } = useAuth();
  const qc = useQueryClient();
  const [days, setDays] = useState<"7" | "30" | "90" | "365">("30");
  const hasExchange = !!user?.exchanges.length;
  const portfolio = useQuery({ queryKey: ["portfolio"], queryFn: () => v2.get<Portfolio>("/portfolio"), enabled: hasExchange, refetchInterval: 60_000 });
  const history = useQuery({
    queryKey: ["portfolio-history", days],
    queryFn: () => v2.get<{ t: string; usd: number; btc: number }[]>("/portfolio/history", { days }),
    enabled: hasExchange,
  });
  const bots = useQuery({ queryKey: ["bots"], queryFn: () => v2.raw<{ data: Bot[]; summary: { total: number; active: number; in_deal: number; profit: number; deals: number } }>("/bots"), refetchInterval: 20_000 });
  const smart = useQuery({ queryKey: ["smart-trades"], queryFn: () => v1.get<{ smart_trades: SmartTrade[] }>("/api/v1/smart_trades/"), enabled: hasExchange, refetchInterval: 20_000 });
  const tx = useQuery({ queryKey: ["transactions", "recent"], queryFn: () => v2.raw<{ data: Transaction[] }>("/transactions", { limit: 6 }) });
  const insights = useInsights();
  const watch = useWatchlist();

  // First visit: take a balance snapshot so the history chart has a starting point.
  const snapped = useRef(false);
  useEffect(() => {
    if (hasExchange && history.data && history.data.length === 0 && !snapped.current) {
      snapped.current = true;
      v2.post("/portfolio/snapshot").then(() => qc.invalidateQueries({ queryKey: ["portfolio-history"] })).catch(() => undefined);
    }
  }, [hasExchange, history.data, qc]);

  const points = useMemo(() => (history.data ?? []).map((p) => ({ t: Date.parse(p.t), v: p.usd })), [history.data]);
  const stats = portfolio.data?.stats ?? {};
  const name = user?.firstName || user?.email.split("@")[0];
  const top = (portfolio.data?.assets ?? []).slice(0, 6);

  return (
    <div className="space-y-5">
      <PageHeader
        title={t("dash.hello", "Hi {name} 👋", { name: name ?? "" })}
        subtitle={t("dash.subtitle", "Here's what's happening with your portfolio today.")}
        actions={
          <>
            <Link to="/trade"><Button variant="secondary" size="sm" icon={<ArrowLeftRight className="size-4" />}>{t("nav.trade", "Trade")}</Button></Link>
            <Link to="/smart-trades"><Button variant="secondary" size="sm" icon={<Target className="size-4" />}>{t("nav.smart", "Smart trades")}</Button></Link>
            <Link to="/bots/new"><Button size="sm" icon={<Plus className="size-4" />}>{t("bots.new", "New bot")}</Button></Link>
          </>
        }
      />

      {!hasExchange && (
        <Card className="flex flex-col items-start gap-4 bg-[linear-gradient(120deg,var(--primary-soft),transparent)] p-6 sm:flex-row sm:items-center">
          <div className="flex size-12 items-center justify-center rounded-2xl bg-primary text-primary-fg"><Plug className="size-6" /></div>
          <div className="flex-1">
            <h2 className="text-lg font-semibold text-fg">{t("dash.onboard_title", "Connect an exchange to get started")}</h2>
            <p className="mt-1 text-sm text-muted">{t("dash.onboard_body", "Link Binance, OKX, Bybit and more with an API key — or start instantly with a $10,000 paper-trading account.")}</p>
          </div>
          <Link to="/exchanges"><Button>{t("dash.onboard_cta", "Connect now")}</Button></Link>
        </Card>
      )}

      {/* KPIs */}
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4">
          {portfolio.isLoading ? <Skeleton className="h-14" /> : (
            <Stat label={t("dash.balance", "Total balance")} value={fmtUsd(portfolio.data?.total_usd ?? user?.balance_usd ?? 0)} hint={`≈ ${(portfolio.data?.total_btc ?? user?.balance_btc ?? 0).toFixed(5)} BTC`} />
          )}
        </Card>
        <Card className="p-4">
          <Stat label={t("dash.pnl24", "24h P&L")} value={fmtUsd(stats.profit_daily_usd ?? 0)} tone={trendClass(stats.profit_daily_usd)} hint={fmtPct(stats.profit_daily_percent_usd ?? 0)} />
        </Card>
        <Card className="p-4">
          <Stat label={t("dash.pnl30", "30d P&L")} value={fmtUsd(stats.profit_monthly_usd ?? 0)} tone={trendClass(stats.profit_monthly_usd)} hint={fmtPct(stats.profit_monthly_percent_usd ?? 0)} />
        </Card>
        <Card className="p-4">
          <Stat
            label={t("dash.bots", "Bots")}
            value={`${bots.data?.summary.active ?? 0} / ${bots.data?.summary.total ?? 0}`}
            hint={<span className={trendClass(bots.data?.summary.profit)}>{t("dash.bot_profit", "Profit")} {fmtUsd(bots.data?.summary.profit ?? 0)}</span>}
          />
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title={t("dash.history", "Balance history")}
            actions={
              <>
                <Segmented size="xs" value={days} onChange={setDays} options={[{ value: "7", label: "7D" }, { value: "30", label: "30D" }, { value: "90", label: "90D" }, { value: "365", label: "1Y" }]} />
                <button type="button" onClick={() => v2.post("/portfolio/snapshot").then(() => { qc.invalidateQueries({ queryKey: ["portfolio"] }); qc.invalidateQueries({ queryKey: ["portfolio-history"] }); })} className="rounded p-1 text-muted hover:text-fg" aria-label={t("dash.refresh", "Refresh")}>
                  <RefreshCw className="size-4" />
                </button>
              </>
            }
          />
          <CardBody className="pt-2">
            {points.length > 1 ? <AreaChart points={points} height={260} valueFormat={usd} /> : (
              <EmptyState icon={<Wallet className="size-6" />} title={t("dash.no_history", "Not enough history yet")} body={t("dash.no_history_b", "Balances are recorded daily (and whenever you refresh). Check back tomorrow for your first trend line.")} className="h-[260px]" />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader title={t("dash.allocation", "Allocation")} actions={<Link to="/portfolio" className="text-xs text-primary hover:underline">{t("common.view_all", "View all")}</Link>} />
          <CardBody>
            {top.length ? (
              <div className="flex flex-col items-center gap-4 sm:flex-row xl:flex-col">
                <Donut
                  items={top.map((a) => ({ label: a.currency, value: a.value }))}
                  center={<><span className="text-xs text-muted">{t("dash.assets", "Assets")}</span><span className="num text-lg font-semibold">{portfolio.data?.assets.length}</span></>}
                />
                <ul className="w-full space-y-2">
                  {top.map((a, i) => (
                    <li key={a.currency} className="flex items-center justify-between text-sm">
                      <span className="flex items-center gap-2"><span className="size-2.5 rounded-sm" style={{ background: donutColor(i) }} />{a.currency}</span>
                      <span className="num text-muted">{fmtUsd(a.value)} · {a.share.toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : (
              <EmptyState title={t("dash.no_assets", "No assets yet")} body={hasExchange ? t("dash.no_assets_b", "Deposit funds or place your first trade.") : undefined} />
            )}
          </CardBody>
        </Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader title={t("dash.active_bots", "Active bots")} actions={<Link to="/bots" className="text-xs text-primary hover:underline">{t("common.view_all", "View all")}</Link>} />
          <CardBody>
            {bots.isLoading ? <Skeleton className="h-32" /> : bots.data?.data.filter((b) => b.isActive).length ? (
              <div className="grid gap-3 md:grid-cols-2">
                {bots.data.data.filter((b) => b.isActive).slice(0, 6).map((b) => <BotRow key={b.id} bot={b} />)}
              </div>
            ) : (
              <EmptyState icon={<BotIcon className="size-6" />} title={t("bots.none", "No active bots")} action={<Link to="/bots/new"><Button size="sm">{t("bots.new", "New bot")}</Button></Link>} />
            )}
          </CardBody>
        </Card>
        <FearGreedCard data={insights.data} />
      </div>

      <div className="grid gap-5 lg:grid-cols-3">
        <Card>
          <CardHeader title={t("nav.smart", "Smart trades")} actions={<Link to="/smart-trades" className="text-xs text-primary hover:underline">{t("common.view_all", "View all")}</Link>} />
          <CardBody className="space-y-3">
            {(smart.data?.smart_trades ?? []).filter((s) => s.isActive).slice(0, 4).map((s) => <SmartTradeRow key={s.id} st={s} />)}
            {smart.data && !smart.data.smart_trades.some((s) => s.isActive) && <EmptyState title={t("smart.none", "No open smart trades")} />}
            {!hasExchange && <EmptyState title={t("smart.none", "No open smart trades")} />}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("watch.title", "Watchlist")} actions={<Link to="/watchlist" className="text-xs text-primary hover:underline">{t("common.manage", "Manage")}</Link>} />
          <CardBody className="space-y-1">
            {(watch.data ?? []).slice(0, 7).map((w) => (
              <Link key={w.id} to={`/markets/${w.symbol.replace("/", "-")}`} className="flex items-center justify-between rounded-lg px-2 py-1.5 hover:bg-surface-2">
                <SymbolCell symbol={w.symbol} />
                <span className="flex items-center gap-3 text-sm"><Price value={w.ticker?.last} /><Change value={w.ticker?.percentage} className="w-16 text-end text-xs" /></span>
              </Link>
            ))}
            {watch.data && !watch.data.length && <EmptyState title={t("watch.empty", "Your watchlist is empty")} body={t("watch.empty_b", "Tap the ☆ next to any market to follow it.")} />}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("dash.recent", "Recent activity")} actions={<Link to="/history" className="text-xs text-primary hover:underline">{t("common.view_all", "View all")}</Link>} />
          <CardBody className="space-y-2">
            {(tx.data?.data ?? []).map((x) => (
              <div key={x.id} className="flex items-center justify-between text-sm">
                <div className="min-w-0">
                  <p className="flex items-center gap-2"><Badge tone={x.type === "buy" ? "up" : "down"}>{x.type}</Badge><span className="truncate text-fg">{x.symbol}</span></p>
                  <p className="mt-0.5 text-xs text-muted">{fmtDateTime(x.created_at)} · {x.exchange}</p>
                </div>
                <span className={cn("num text-sm", x.status ? "text-fg" : "text-down")}>{x.status ? fmtUsd(x.value) : t("common.failed", "Failed")}</span>
              </div>
            ))}
            {tx.data && !tx.data.data.length && <EmptyState title={t("dash.no_activity", "No trades yet")} />}
          </CardBody>
        </Card>
      </div>
    </div>
  );
}
