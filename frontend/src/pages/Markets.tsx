import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ChartCandlestick, Search, TrendingDown, TrendingUp, Flame } from "lucide-react";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import { mergeLive, useLiveTickers, useMarketExchange, useTickers } from "../lib/hooks";
import type { Coin, Overview, Signal, Ticker } from "../lib/types";
import { fmtCompact, fmtPct, fmtPrice, symbolToSlug } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Card, CardBody, CardHeader, CoinIcon, Input, PageHeader, Segmented, Skeleton, Table, Tabs, Td, Th } from "../components/ui";
import { Change, Price, RecBadge, SymbolCell, TickerTable } from "../components/market";

function MoversCard({ title, icon, rows, tone }: { title: string; icon: React.ReactNode; rows?: Ticker[]; tone: "up" | "down" | "primary" }) {
  return (
    <Card>
      <CardHeader title={<span className="flex items-center gap-2">{icon}{title}</span>} />
      <div className="p-2">
        {!rows ? <Skeleton className="m-2 h-40" /> : rows.slice(0, 5).map((r) => (
          <Link key={r.symbol} to={`/markets/${symbolToSlug(r.symbol)}`} className="flex items-center justify-between rounded-lg px-3 py-2 hover:bg-surface-2">
            <SymbolCell symbol={r.symbol} />
            <span className="flex items-center gap-3 text-sm">
              <Price value={r.last} className="text-fg" />
              {tone === "primary" ? <span className="num w-20 text-end text-muted">{fmtCompact(r.quoteVolume, "$")}</span> : <Change value={r.percentage} className="w-20 text-end" />}
            </span>
          </Link>
        ))}
      </div>
    </Card>
  );
}

function Heatmap({ rows }: { rows: Ticker[] }) {
  const top = rows.slice(0, 30);
  const maxVol = Math.max(1, ...top.map((r) => r.quoteVolume));
  return (
    <div className="grid grid-cols-3 gap-1.5 sm:grid-cols-5 lg:grid-cols-6">
      {top.map((r) => {
        const p = Math.max(-10, Math.min(10, r.percentage));
        const alpha = 0.18 + (Math.abs(p) / 10) * 0.6;
        const bg = p >= 0 ? `rgb(34 197 94 / ${alpha})` : `rgb(242 85 90 / ${alpha})`;
        const big = r.quoteVolume / maxVol > 0.25;
        return (
          <Link
            key={r.symbol}
            to={`/markets/${symbolToSlug(r.symbol)}`}
            className={cn("flex flex-col justify-between rounded-lg p-2.5 text-white transition-transform hover:scale-[1.02]", big && "sm:col-span-2")}
            style={{ background: bg, minHeight: big ? 96 : 76 }}
          >
            <span className="text-sm font-semibold text-fg">{r.symbol.split("/")[0]}</span>
            <span className="num text-xs text-fg/80">{fmtPrice(r.last)}</span>
            <span className={cn("num text-sm font-semibold", p >= 0 ? "text-up" : "text-down")}>{fmtPct(r.percentage)}</span>
          </Link>
        );
      })}
    </div>
  );
}

function CoinsTable() {
  const t = useT();
  const coins = useQuery({ queryKey: ["coins", 100], queryFn: () => v2.get<Coin[]>("/insights/coins", { limit: 100 }), staleTime: 5 * 60_000 });
  if (coins.isLoading) return <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>;
  const src = coins.data?.[0]?.source;
  return (
    <>
      <Table>
        <thead>
          <tr>
            <Th>#</Th>
            <Th>{t("market.coin", "Coin")}</Th>
            <Th align="end">{t("market.price", "Price")}</Th>
            <Th align="end">24h</Th>
            <Th align="end">7d</Th>
            <Th align="end">{t("market.mcap", "Market cap")}</Th>
            <Th align="end">{t("market.volume", "Volume")}</Th>
          </tr>
        </thead>
        <tbody>
          {(coins.data ?? []).map((c) => (
            <tr key={c.id} className="hover:bg-surface-2/60">
              <Td className="num text-muted">{c.rank}</Td>
              <Td>
                <Link to={`/markets/${c.symbol}-USDT`} className="flex items-center gap-2.5">
                  <CoinIcon symbol={c.symbol} src={c.image} size={22} />
                  <span className="font-medium text-fg">{c.name}</span>
                  <span className="text-xs text-muted">{c.symbol}</span>
                </Link>
              </Td>
              <Td align="end" className="num text-fg">{fmtPrice(c.price)}</Td>
              <Td align="end"><Change value={c.change_24h} /></Td>
              <Td align="end"><Change value={c.change_7d} /></Td>
              <Td align="end" className="num text-muted">{fmtCompact(c.market_cap, "$")}</Td>
              <Td align="end" className="num text-muted">{fmtCompact(c.volume, "$")}</Td>
            </tr>
          ))}
        </tbody>
      </Table>
      <p className="px-5 py-3 text-xs text-muted">
        {src === "coingecko" ? (
          <>{t("market.cg_attr", "Market cap data by")} <a className="hover:text-fg" href="https://www.coingecko.com" target="_blank" rel="noreferrer">CoinGecko</a></>
        ) : t("pulse.demo", "Demo data")}
      </p>
    </>
  );
}

function SignalsTable() {
  const t = useT();
  const ex = useMarketExchange();
  const [interval, setIv] = useState("1h");
  const signals = useQuery({ queryKey: ["signals", ex, interval], queryFn: () => v2.get<Signal[]>("/market/signals", { exchange: ex, interval, top: 24 }), staleTime: 60_000 });
  return (
    <>
      <div className="flex justify-end px-5 pt-3">
        <Segmented size="xs" value={interval} onChange={setIv} options={["15m", "1h", "4h", "1d"].map((v) => ({ value: v, label: v }))} />
      </div>
      {signals.isLoading ? <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div> : (
        <Table>
          <thead>
            <tr>
              <Th>{t("market.pair", "Pair")}</Th>
              <Th align="end">{t("market.price", "Price")}</Th>
              <Th align="center">{t("ta.summary", "Summary")}</Th>
              <Th align="center">{t("ta.oscillators", "Oscillators")}</Th>
              <Th align="center">{t("ta.moving_averages", "Moving averages")}</Th>
              <Th align="end">RSI</Th>
            </tr>
          </thead>
          <tbody>
            {(signals.data ?? []).map((s) => (
              <tr key={s.symbol} className="hover:bg-surface-2/60">
                <Td><Link to={`/markets/${symbolToSlug(s.symbol)}`}><SymbolCell symbol={s.symbol} /></Link></Td>
                <Td align="end" className="num text-fg">{fmtPrice(s.price)}</Td>
                <Td align="center"><RecBadge rec={s.RECOMMENDATION} /></Td>
                <Td align="center"><RecBadge rec={s.oscillators} /></Td>
                <Td align="center"><RecBadge rec={s.moving_averages} /></Td>
                <Td align="end" className={cn("num", (s.rsi ?? 50) > 70 ? "text-down" : (s.rsi ?? 50) < 30 ? "text-up" : "text-muted")}>{s.rsi?.toFixed(1) ?? "—"}</Td>
              </tr>
            ))}
          </tbody>
        </Table>
      )}
    </>
  );
}

export default function Markets() {
  const t = useT();
  const [quote, setQuote] = useState("USDT");
  const [q, setQ] = useState("");
  const [tab, setTab] = useState<"spot" | "coins" | "signals" | "heatmap">("spot");
  const tickers = useTickers(quote, 500);
  const live = useLiveTickers(tab === "spot" || tab === "heatmap");
  const overview = useQuery({ queryKey: ["overview", quote], queryFn: () => v2.get<Overview>("/market/overview", { quote }), refetchInterval: 30_000 });

  const rows = useMemo(() => {
    const all = (tickers.data ?? []).map((r) => mergeLive(r, live));
    const needle = q.trim().toUpperCase();
    return needle ? all.filter((r) => r.symbol.includes(needle)) : all;
  }, [tickers.data, live, q]);

  const breadth = overview.data?.breadth;
  return (
    <div className="space-y-5">
      <PageHeader
        icon={<ChartCandlestick className="size-5" />}
        title={t("nav.markets", "Markets")}
        subtitle={t("markets.subtitle", "Live spot markets, movers, signals and market caps.")}
        actions={breadth && (
          <div className="flex items-center gap-2 text-xs">
            <Badge tone="up">▲ {breadth.up}</Badge>
            <Badge tone="down">▼ {breadth.down}</Badge>
            <Badge>{t("markets.flat", "flat")} {breadth.flat}</Badge>
          </div>
        )}
      />
      <div className="grid gap-4 lg:grid-cols-3">
        <MoversCard title={t("markets.gainers", "Top gainers")} icon={<TrendingUp className="size-4 text-up" />} rows={overview.data?.gainers} tone="up" />
        <MoversCard title={t("markets.losers", "Top losers")} icon={<TrendingDown className="size-4 text-down" />} rows={overview.data?.losers} tone="down" />
        <MoversCard title={t("markets.volume", "Highest volume")} icon={<Flame className="size-4 text-primary" />} rows={overview.data?.volume} tone="primary" />
      </div>

      <Card>
        <div className="flex flex-wrap items-center justify-between gap-3 px-4 pt-3 sm:px-5">
          <Tabs
            value={tab}
            onChange={setTab}
            className="border-0"
            tabs={[
              { value: "spot", label: t("markets.spot", "Spot") },
              { value: "heatmap", label: t("markets.heatmap", "Heatmap") },
              { value: "signals", label: t("markets.signals", "Signals") },
              { value: "coins", label: t("markets.coins", "Top coins") },
            ]}
          />
          {(tab === "spot" || tab === "heatmap") && (
            <div className="flex flex-wrap items-center gap-2">
              <Segmented size="xs" value={quote} onChange={setQuote} options={["USDT", "USDC", "BTC", "ETH"].map((v) => ({ value: v, label: v }))} />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("market.search_pair", "Search pair…")} prefix={<Search className="size-4" />} className="w-48" />
            </div>
          )}
        </div>
        <div className="mt-3 border-t border-line">
          {tab === "spot" && <TickerTable rows={rows} loading={tickers.isLoading} limit={q ? undefined : 150} />}
          {tab === "heatmap" && <CardBody>{rows.length ? <Heatmap rows={rows} /> : <Skeleton className="h-64" />}</CardBody>}
          {tab === "signals" && <SignalsTable />}
          {tab === "coins" && <CoinsTable />}
        </div>
      </Card>
    </div>
  );
}
