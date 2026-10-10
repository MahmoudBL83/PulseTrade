import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PieChart, RefreshCw, RotateCcw } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import type { Performance, Portfolio as PortfolioT } from "../lib/types";
import { fmtAmount, fmtNum, fmtPct, fmtPrice, fmtUsd, trendClass } from "../lib/format";
import { Button, Card, CardBody, CardHeader, ConfirmButton, EmptyState, Notice, PageHeader, Segmented, Skeleton, Stat, Table, Td, Th } from "../components/ui";
import { AreaChart, Donut, donutColor } from "../components/charts";
import { CoinIcon } from "../components/ui";

const usd = (v: number) => fmtUsd(v);

export default function Portfolio() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [days, setDays] = useState<"30" | "90" | "365">("90");
  const [unit, setUnit] = useState<"usd" | "btc">("usd");
  const p = useQuery({ queryKey: ["portfolio"], queryFn: () => v2.get<PortfolioT>("/portfolio"), enabled: !!user?.exchanges.length });
  const hist = useQuery({ queryKey: ["portfolio-history", days], queryFn: () => v2.get<{ t: string; usd: number; btc: number }[]>("/portfolio/history", { days }), enabled: !!user?.exchanges.length });
  const perf = useQuery({ queryKey: ["performance", days], queryFn: () => v2.get<Performance>("/portfolio/performance", { days }), enabled: !!user });
  const points = useMemo(() => (hist.data ?? []).map((x) => ({ t: Date.parse(x.t), v: unit === "usd" ? x.usd : x.btc })), [hist.data, unit]);

  const snapshot = useMutation({
    mutationFn: () => v2.post<PortfolioT>("/portfolio/snapshot"),
    onSuccess: () => {
      toast.success(t("portfolio.refreshed", "Balances refreshed"));
      qc.invalidateQueries({ queryKey: ["portfolio"] });
      qc.invalidateQueries({ queryKey: ["portfolio-history"] });
      qc.invalidateQueries({ queryKey: ["performance"] });
    },
    onError: (e) => toast.error(e),
  });

  if (!user?.exchanges.length) {
    return (
      <>
        <PageHeader icon={<PieChart className="size-5" />} title={t("nav.portfolio", "Portfolio")} />
        <Card><EmptyState title={t("dash.onboard_title", "Connect an exchange to get started")} action={<Link to="/exchanges"><Button>{t("dash.onboard_cta", "Connect now")}</Button></Link>} /></Card>
      </>
    );
  }

  const pf = perf.data;
  const assets = p.data?.assets ?? [];
  return (
    <div className="space-y-5">
      <PageHeader
        icon={<PieChart className="size-5" />}
        title={t("nav.portfolio", "Portfolio")}
        subtitle={t("portfolio.subtitle", "All balances across your connected exchanges.")}
        actions={
          <>
            <Button variant="secondary" size="sm" icon={<RefreshCw className="size-4" />} loading={snapshot.isPending} onClick={() => snapshot.mutate()}>{t("portfolio.refresh", "Refresh balances")}</Button>
            <ConfirmButton
              variant="secondary"
              title={t("portfolio.reset_q", "Reset your statistics?")}
              body={t("portfolio.reset_b", "Balance history and profit statistics are cleared. Your exchange balances are not touched.")}
              confirmLabel={t("portfolio.reset", "Reset stats")}
              onConfirm={async () => {
                await v1.get("/api/v1/reset_stats");
                qc.invalidateQueries();
                toast.success(t("portfolio.reset_done", "Statistics reset"));
              }}
            >
              <RotateCcw className="size-4" />
            </ConfirmButton>
          </>
        }
      />
      {!!p.data?.errors.length && (
        <Notice tone="warning">{t("portfolio.partial", "Some exchanges could not be read:")} {p.data.errors.map((e) => e.exchange).join(", ")}</Notice>
      )}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4">{p.isLoading ? <Skeleton className="h-14" /> : <Stat label={t("dash.balance", "Total balance")} value={fmtUsd(p.data?.total_usd)} hint={`≈ ${(p.data?.total_btc ?? 0).toFixed(6)} BTC`} />}</Card>
        <Card className="p-4"><Stat label={t("portfolio.return", "Return ({d}d)", { d: days })} value={fmtPct(pf?.return_pct ?? 0)} tone={trendClass(pf?.return_pct)} hint={pf?.cagr ? `CAGR ${fmtPct(pf.cagr)}` : undefined} /></Card>
        <Card className="p-4"><Stat label={t("portfolio.mdd", "Max drawdown")} value={fmtPct(-(pf?.max_drawdown ?? 0))} tone="text-down" hint={`${t("portfolio.vol", "Volatility")} ${fmtPct(pf?.volatility ?? 0, 1, false)}`} /></Card>
        <Card className="p-4"><Stat label="Sharpe / Sortino" value={`${fmtNum(pf?.sharpe ?? 0)} / ${fmtNum(pf?.sortino ?? 0)}`} hint={`Calmar ${fmtNum(pf?.calmar ?? 0)}`} /></Card>
      </div>

      <div className="grid gap-5 xl:grid-cols-3">
        <Card className="xl:col-span-2">
          <CardHeader
            title={t("dash.history", "Balance history")}
            actions={
              <>
                <Segmented size="xs" value={unit} onChange={setUnit} options={[{ value: "usd", label: "USD" }, { value: "btc", label: "BTC" }]} />
                <Segmented size="xs" value={days} onChange={setDays} options={[{ value: "30", label: "30D" }, { value: "90", label: "90D" }, { value: "365", label: "1Y" }]} />
              </>
            }
          />
          <CardBody className="pt-2">
            {points.length > 1 ? <AreaChart points={points} height={280} valueFormat={unit === "usd" ? usd : undefined} /> : <EmptyState title={t("dash.no_history", "Not enough history yet")} body={t("dash.no_history_b", "Balances are recorded daily (and whenever you refresh). Check back tomorrow for your first trend line.")} className="h-[280px]" />}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("dash.allocation", "Allocation")} />
          <CardBody className="flex flex-col items-center gap-4">
            {assets.length ? (
              <>
                <Donut items={assets.slice(0, 8).map((a) => ({ label: a.currency, value: a.value }))} size={190} center={<span className="num text-lg font-semibold">{fmtUsd(p.data?.total_usd, 0)}</span>} />
                <ul className="w-full space-y-1.5 text-sm">
                  {assets.slice(0, 8).map((a, i) => (
                    <li key={a.currency} className="flex items-center justify-between">
                      <span className="flex items-center gap-2"><span className="size-2.5 rounded-sm" style={{ background: donutColor(i) }} />{a.currency}</span>
                      <span className="num text-muted">{a.share.toFixed(1)}%</span>
                    </li>
                  ))}
                </ul>
              </>
            ) : <EmptyState title={t("dash.no_assets", "No assets yet")} />}
          </CardBody>
        </Card>
      </div>

      <Card>
        <CardHeader title={t("portfolio.holdings", "Holdings")} subtitle={p.data ? t("portfolio.n_assets", "{n} assets", { n: assets.length }) : undefined} />
        {p.isLoading ? <Skeleton className="m-4 h-40" /> : assets.length ? (
          <Table>
            <thead>
              <tr>
                <Th>{t("portfolio.asset", "Asset")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("portfolio.total", "Total")}</Th>
                <Th align="end">{t("portfolio.free", "Free")}</Th><Th align="end">{t("portfolio.in_orders", "In orders")}</Th><Th align="end">{t("tx.value", "Value")}</Th><Th align="end">%</Th><Th>{t("nav.exchanges", "Exchanges")}</Th>
              </tr>
            </thead>
            <tbody>
              {assets.map((a) => (
                <tr key={a.currency}>
                  <Td><span className="flex items-center gap-2"><CoinIcon symbol={a.currency} size={22} /><span className="font-medium text-fg">{a.currency}</span></span></Td>
                  <Td align="end" className="num">{fmtPrice(a.price)}</Td>
                  <Td align="end" className="num">{fmtAmount(a.total)}</Td>
                  <Td align="end" className="num text-muted">{fmtAmount(a.free)}</Td>
                  <Td align="end" className="num text-muted">{fmtAmount(a.used)}</Td>
                  <Td align="end" className="num text-fg">{fmtUsd(a.value)}</Td>
                  <Td align="end" className="num text-muted">{a.share.toFixed(1)}</Td>
                  <Td className="text-xs text-muted capitalize">{a.exchanges.join(", ")}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        ) : <EmptyState title={t("dash.no_assets", "No assets yet")} />}
      </Card>

      {pf && (
        <div className="grid gap-5 lg:grid-cols-2">
          <Card>
            <CardHeader title={t("portfolio.bots_perf", "Bot performance")} />
            <CardBody className="grid grid-cols-2 gap-4">
              <Stat label={t("bots.profit", "Realized profit")} value={fmtUsd(pf.bot_profit)} tone={trendClass(pf.bot_profit)} />
              <Stat label={t("bt.winrate", "Win rate")} value={fmtPct(pf.bot_win_rate, 1, false)} hint={`${pf.bot_deals} ${t("bt.deals", "deals")}`} />
              <Stat label={t("portfolio.best_bot", "Best bot")} value={pf.best_bot ? pf.best_bot.name : "—"} hint={pf.best_bot ? fmtUsd(pf.best_bot.profit) : undefined} />
              <Stat label={t("portfolio.worst_bot", "Weakest bot")} value={pf.worst_bot ? pf.worst_bot.name : "—"} hint={pf.worst_bot ? fmtUsd(pf.worst_bot.profit) : undefined} />
            </CardBody>
          </Card>
          <Card>
            <CardHeader title={t("portfolio.activity", "Trading activity (30d)")} />
            <CardBody className="grid grid-cols-2 gap-4">
              <Stat label={t("portfolio.trades", "Trades")} value={pf.trades_30d} />
              <Stat label={t("portfolio.volume", "Volume")} value={fmtUsd(pf.volume_30d, 0)} />
              <Stat label={t("nav.smart", "Smart trades")} value={`${pf.smart_trades_active} / ${pf.smart_trades_total}`} />
              <Stat label={t("portfolio.smart_profit", "Smart trade profit")} value={fmtUsd(pf.smart_trade_profit)} tone={trendClass(pf.smart_trade_profit)} />
              <Stat label={t("portfolio.best_day", "Best day")} value={fmtPct(pf.best_day)} tone="text-up" />
              <Stat label={t("portfolio.worst_day", "Worst day")} value={fmtPct(pf.worst_day)} tone="text-down" />
            </CardBody>
          </Card>
        </div>
      )}
    </div>
  );
}
