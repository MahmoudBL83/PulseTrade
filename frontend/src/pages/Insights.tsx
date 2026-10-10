import { useMemo } from "react";
import { Link } from "react-router";
import { Gauge as GaugeIcon, Landmark, Flame } from "lucide-react";
import { useT } from "../i18n";
import { fmtCompact, fmtDate, fmtPct, fmtPrice, trendClass } from "../lib/format";
import { Card, CardBody, CardHeader, CoinIcon, PageHeader, Skeleton, Stat } from "../components/ui";
import { AreaChart, Bars } from "../components/charts";
import { FearGreedCard, useInsights } from "./Dashboard";

function Attribution({ source, map }: { source: string; map: Record<string, { name: string; url: string | null }> }) {
  const t = useT();
  const a = map[source];
  if (!a) return null;
  return a.url ? (
    <a href={a.url} target="_blank" rel="noreferrer" className="text-[11px] text-muted hover:text-fg">{t("pulse.source", "Source")}: {a.name}</a>
  ) : (
    <span className="text-[11px] text-muted">{a.name}</span>
  );
}

const fngFormat = (v: number) => v.toFixed(0);

export default function Insights() {
  const t = useT();
  const q = useInsights();
  const d = q.data;
  const fngPoints = useMemo(() => (d?.fear_greed.history ?? []).map((p) => ({ t: p.timestamp * 1000, v: p.value })), [d]);

  return (
    <div className="space-y-5">
      <PageHeader icon={<GaugeIcon className="size-5" />} title={t("nav.insights", "Market pulse")} subtitle={t("pulse.subtitle", "Sentiment, market capitalisation and DeFi activity at a glance.")} />
      {!d ? <Skeleton className="h-96" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
            <Card className="p-4"><Stat label={t("pulse.mcap", "Total market cap")} value={fmtCompact(d.global.total_market_cap_usd, "$")} hint={<span className={trendClass(d.global.market_cap_change_24h)}>{fmtPct(d.global.market_cap_change_24h)} 24h</span>} /></Card>
            <Card className="p-4"><Stat label={t("pulse.volume", "24h volume")} value={fmtCompact(d.global.total_volume_usd, "$")} /></Card>
            <Card className="p-4"><Stat label={t("pulse.dominance", "BTC / ETH dominance")} value={`${d.global.btc_dominance.toFixed(1)}% / ${d.global.eth_dominance.toFixed(1)}%`} /></Card>
            <Card className="p-4"><Stat label={t("pulse.coins", "Active coins")} value={fmtCompact(d.global.active_cryptocurrencies)} hint={`${fmtCompact(d.global.markets)} ${t("pulse.markets", "markets")}`} /></Card>
          </div>
          <div className="grid gap-5 xl:grid-cols-3">
            <FearGreedCard data={d} />
            <Card className="xl:col-span-2">
              <CardHeader title={t("pulse.fng_history", "Fear & Greed — 30 days")} actions={<Attribution source={d.fear_greed.source} map={d.attribution} />} />
              <CardBody className="pt-2"><AreaChart points={fngPoints} height={240} tone="primary" valueFormat={fngFormat} /></CardBody>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title={<span className="flex items-center gap-2"><Flame className="size-4 text-primary" />{t("pulse.trending", "Trending coins")}</span>} actions={<Attribution source={d.trending[0]?.source ?? "synthetic"} map={d.attribution} />} />
              <CardBody className="space-y-1">
                {d.trending.map((c) => (
                  <Link key={c.id} to={`/markets/${c.symbol}-USDT`} className="flex items-center justify-between rounded-lg px-2 py-2 hover:bg-surface-2">
                    <span className="flex items-center gap-2.5">
                      <CoinIcon symbol={c.symbol} src={c.image} size={24} />
                      <span className="font-medium text-fg">{c.name}</span>
                      <span className="text-xs text-muted">{c.symbol}{c.rank ? ` · #${c.rank}` : ""}</span>
                    </span>
                    <span className="flex items-center gap-3 text-sm">
                      {c.price !== null && <span className="num text-fg">{fmtPrice(c.price)}</span>}
                      {c.change_24h !== null && <span className={`num w-16 text-end ${trendClass(c.change_24h)}`}>{fmtPct(c.change_24h)}</span>}
                    </span>
                  </Link>
                ))}
              </CardBody>
            </Card>
            <Card>
              <CardHeader title={<span className="flex items-center gap-2"><Landmark className="size-4 text-info" />{t("pulse.defi", "DeFi by chain")}</span>} actions={<Attribution source={d.defi.source} map={d.attribution} />} />
              <CardBody className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <Stat label={t("pulse.tvl", "DeFi TVL")} value={fmtCompact(d.defi.total_tvl, "$")} />
                  <Stat label={t("pulse.stables", "Stablecoin supply")} value={d.defi.stablecoin_supply ? fmtCompact(d.defi.stablecoin_supply, "$") : "—"} />
                </div>
                <Bars items={d.defi.chains.slice(0, 10).map((c) => ({ label: c.name, value: c.tvl }))} format={(v) => fmtCompact(v, "$")} />
              </CardBody>
            </Card>
          </div>
          <p className="text-xs text-muted">{t("pulse.updated", "Updated")} {fmtDate(d.updated_at)} · {t("pulse.cache", "cached for a few minutes to respect the free APIs' limits")}</p>
        </>
      )}
    </div>
  );
}
