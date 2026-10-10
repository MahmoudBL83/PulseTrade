import { useMemo, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, Star } from "lucide-react";
import type { Analysis, OrderBook, Recommendation, Ticker, Trade, WatchItem } from "../lib/types";
import { baseOf, fmtAmount, fmtCompact, fmtPct, fmtPrice, fmtTime, symbolToSlug, trendClass } from "../lib/format";
import { cn, useDebounced, useFlash } from "../lib/utils";
import { useT } from "../i18n";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { v2 } from "../lib/api";
import { useSymbols } from "../lib/hooks";
import { Badge, CoinIcon, Input, Skeleton, Td, Th, Table } from "./ui";

/* ------------------------------------------------------------------ price + change */

export function Price({ value, className }: { value: number | null | undefined; className?: string }) {
  const flash = useFlash(value);
  return <span className={cn("num rounded px-0.5", flash, className)}>{fmtPrice(value)}</span>;
}

export function Change({ value, className, arrow = false }: { value: number | null | undefined; className?: string; arrow?: boolean }) {
  const up = (value ?? 0) >= 0;
  return (
    <span className={cn("num inline-flex items-center gap-0.5", trendClass(value), className)}>
      {arrow && value !== 0 && (up ? <ArrowUp className="size-3" /> : <ArrowDown className="size-3" />)}
      {fmtPct(value)}
    </span>
  );
}

export function SymbolCell({ symbol, image }: { symbol: string; image?: string | null }) {
  const [base, quote] = symbol.split("/");
  return (
    <span className="flex items-center gap-2.5">
      <CoinIcon symbol={symbol} src={image} size={22} />
      <span className="font-medium text-fg">{base}</span>
      <span className="text-xs text-muted">/{quote}</span>
    </span>
  );
}

/* ------------------------------------------------------------------ watch star */

export function useWatchlist() {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["watchlist"],
    queryFn: () => v2.get<WatchItem[]>("/watchlist"),
    enabled: !!user,
    refetchInterval: 20_000,
  });
}

export function WatchStar({ symbol }: { symbol: string }) {
  const t = useT();
  const { user } = useAuth();
  const toast = useToast();
  const qc = useQueryClient();
  const list = useWatchlist();
  const item = list.data?.find((w) => w.symbol === symbol);
  const toggle = useMutation({
    mutationFn: () => (item ? v2.del(`/watchlist/${item.id}`) : v2.post("/watchlist", { symbol })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["watchlist"] }),
    onError: (e) => toast.error(e),
  });
  if (!user) return null;
  return (
    <button
      type="button"
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        toggle.mutate();
      }}
      aria-pressed={!!item}
      aria-label={item ? t("watch.remove", "Remove from watchlist") : t("watch.add", "Add to watchlist")}
      className="rounded p-1 text-muted hover:text-primary"
    >
      <Star className={cn("size-4", item && "fill-primary text-primary")} />
    </button>
  );
}

/* ------------------------------------------------------------------ ticker table */

type SortKey = "symbol" | "last" | "percentage" | "quoteVolume" | "high" | "low";

export function TickerTable({ rows, loading, limit, compact }: { rows: Ticker[]; loading?: boolean; limit?: number; compact?: boolean }) {
  const t = useT();
  const [sort, setSort] = useState<{ key: SortKey; dir: "asc" | "desc" }>({ key: "quoteVolume", dir: "desc" });
  const sorted = useMemo(() => {
    const out = [...rows].sort((a, b) => {
      const av = a[sort.key], bv = b[sort.key];
      const cmp = typeof av === "string" ? av.localeCompare(bv as string) : (av as number) - (bv as number);
      return sort.dir === "asc" ? cmp : -cmp;
    });
    return limit ? out.slice(0, limit) : out;
  }, [rows, sort, limit]);
  const head = (key: SortKey, label: string, align: "start" | "end" = "end") => (
    <Th align={align} onClick={() => setSort((s) => ({ key, dir: s.key === key && s.dir === "desc" ? "asc" : "desc" }))} sorted={sort.key === key ? sort.dir : null}>
      {label}
    </Th>
  );
  if (loading) return <div className="space-y-2 p-4">{Array.from({ length: 8 }).map((_, i) => <Skeleton key={i} className="h-9" />)}</div>;
  return (
    <Table>
      <thead>
        <tr>
          {head("symbol", t("market.pair", "Pair"), "start")}
          {head("last", t("market.price", "Price"))}
          {head("percentage", t("market.change24", "24h %"))}
          {!compact && head("high", t("market.high", "24h high"))}
          {!compact && head("low", t("market.low", "24h low"))}
          {head("quoteVolume", t("market.volume", "Volume"))}
          <Th align="end"><span className="sr-only">{t("watch.title", "Watchlist")}</span></Th>
        </tr>
      </thead>
      <tbody>
        {sorted.map((r) => (
          <tr key={r.symbol} className="group hover:bg-surface-2/60">
            <Td>
              <Link to={`/markets/${symbolToSlug(r.symbol)}`} className="block"><SymbolCell symbol={r.symbol} /></Link>
            </Td>
            <Td align="end"><Price value={r.last} className="text-fg" /></Td>
            <Td align="end"><Change value={r.percentage} /></Td>
            {!compact && <Td align="end" className="num text-muted">{fmtPrice(r.high)}</Td>}
            {!compact && <Td align="end" className="num text-muted">{fmtPrice(r.low)}</Td>}
            <Td align="end" className="num text-muted">{fmtCompact(r.quoteVolume, "$")}</Td>
            <Td align="end"><WatchStar symbol={r.symbol} /></Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

/* ------------------------------------------------------------------ order book & trades */

export function OrderBookView({ book, onPick, rows = 12 }: { book?: OrderBook; onPick?: (price: number) => void; rows?: number }) {
  const t = useT();
  if (!book) return <div className="space-y-1 p-3">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-5" />)}</div>;
  const asks = book.asks.slice(0, rows).reverse();
  const bids = book.bids.slice(0, rows);
  const max = Math.max(1, ...asks.map((a) => a[1]), ...bids.map((b) => b[1]));
  const spread = book.asks[0] && book.bids[0] ? book.asks[0][0] - book.bids[0][0] : 0;
  const mid = book.asks[0] && book.bids[0] ? (book.asks[0][0] + book.bids[0][0]) / 2 : 0;
  const row = (p: number, a: number, side: "bid" | "ask") => (
    <button
      key={`${side}${p}`}
      type="button"
      onClick={() => onPick?.(p)}
      className="relative grid w-full grid-cols-3 px-3 py-0.5 text-xs hover:bg-surface-2"
    >
      <span className={cn("absolute inset-y-0 end-0", side === "bid" ? "bg-up-soft" : "bg-down-soft")} style={{ width: `${(a / max) * 100}%` }} />
      <span className={cn("num relative text-start", side === "bid" ? "text-up" : "text-down")}>{fmtPrice(p)}</span>
      <span className="num relative text-end text-fg">{fmtAmount(a)}</span>
      <span className="num relative text-end text-muted">{fmtCompact(a * p)}</span>
    </button>
  );
  return (
    <div dir="ltr">
      <div className="grid grid-cols-3 px-3 py-1.5 text-[11px] text-muted">
        <span>{t("market.price", "Price")}</span>
        <span className="text-end">{t("market.amount", "Amount")}</span>
        <span className="text-end">{t("market.total", "Total")}</span>
      </div>
      {asks.map(([p, a]) => row(p, a, "ask"))}
      <div className="flex items-center justify-between border-y border-line px-3 py-1.5">
        <span className="num text-sm font-semibold text-fg">{fmtPrice(mid)}</span>
        <span className="num text-[11px] text-muted">{t("market.spread", "Spread")} {fmtPrice(spread)}</span>
      </div>
      {bids.map(([p, a]) => row(p, a, "bid"))}
    </div>
  );
}

export function TradesTape({ trades }: { trades?: Trade[] }) {
  const t = useT();
  if (!trades) return <div className="space-y-1 p-3">{Array.from({ length: 10 }).map((_, i) => <Skeleton key={i} className="h-5" />)}</div>;
  return (
    <div dir="ltr">
      <div className="grid grid-cols-3 px-3 py-1.5 text-[11px] text-muted">
        <span>{t("market.price", "Price")}</span>
        <span className="text-end">{t("market.amount", "Amount")}</span>
        <span className="text-end">{t("market.time", "Time")}</span>
      </div>
      {trades.slice(0, 24).map((tr) => (
        <div key={tr.id + tr.timestamp} className="grid grid-cols-3 px-3 py-0.5 text-xs">
          <span className={cn("num", tr.side === "buy" ? "text-up" : "text-down")}>{fmtPrice(tr.price)}</span>
          <span className="num text-end text-fg">{fmtAmount(tr.amount)}</span>
          <span className="num text-end text-muted">{fmtTime(tr.timestamp)}</span>
        </div>
      ))}
    </div>
  );
}

/* ------------------------------------------------------------------ analysis */

const recTone: Record<Recommendation, "up" | "down" | "neutral"> = {
  STRONG_BUY: "up", BUY: "up", NEUTRAL: "neutral", SELL: "down", STRONG_SELL: "down",
};

export function RecBadge({ rec }: { rec: Recommendation }) {
  const t = useT();
  const labels: Record<Recommendation, string> = {
    STRONG_BUY: t("ta.strong_buy", "Strong buy"), BUY: t("ta.buy", "Buy"), NEUTRAL: t("ta.neutral", "Neutral"),
    SELL: t("ta.sell", "Sell"), STRONG_SELL: t("ta.strong_sell", "Strong sell"),
  };
  return <Badge tone={recTone[rec]}>{labels[rec]}</Badge>;
}

export function AnalysisPanel({ a }: { a?: Analysis }) {
  const t = useT();
  if (!a) return <div className="space-y-2 p-4"><Skeleton className="h-16" /><Skeleton className="h-40" /></div>;
  const block = (title: string, b: Analysis["summary"]) => {
    const total = b.BUY + b.SELL + b.NEUTRAL || 1;
    return (
      <div className="rounded-xl border border-line p-3">
        <div className="mb-2 flex items-center justify-between">
          <span className="text-xs font-medium text-muted">{title}</span>
          <RecBadge rec={b.RECOMMENDATION} />
        </div>
        <div className="flex h-2 overflow-hidden rounded-full bg-surface-3" dir="ltr">
          <div className="bg-down" style={{ width: `${(b.SELL / total) * 100}%` }} />
          <div className="bg-muted/40" style={{ width: `${(b.NEUTRAL / total) * 100}%` }} />
          <div className="bg-up" style={{ width: `${(b.BUY / total) * 100}%` }} />
        </div>
        <div className="num mt-1.5 flex justify-between text-[11px] text-muted" dir="ltr">
          <span className="text-down">{t("ta.sell", "Sell")} {b.SELL}</span>
          <span>{t("ta.neutral", "Neutral")} {b.NEUTRAL}</span>
          <span className="text-up">{t("ta.buy", "Buy")} {b.BUY}</span>
        </div>
      </div>
    );
  };
  const ind = a.indicators;
  const rows: [string, string, number | null | undefined, string | undefined][] = [
    ["RSI (14)", "RSI", ind.RSI, a.oscillators.COMPUTE?.RSI],
    ["MACD (12,26)", "MACD.macd", ind["MACD.macd"], a.oscillators.COMPUTE?.MACD],
    ["Stoch %K", "Stoch.K", ind["Stoch.K"], a.oscillators.COMPUTE?.["STOCH.K"]],
    ["CCI (20)", "CCI20", ind.CCI20, a.oscillators.COMPUTE?.CCI],
    ["ADX (14)", "ADX", ind.ADX, a.oscillators.COMPUTE?.ADX],
    ["Williams %R", "W.R", ind["W.R"], a.oscillators.COMPUTE?.["W%R"]],
    ["EMA 20", "EMA20", ind.EMA20, a.moving_averages.COMPUTE?.EMA20],
    ["EMA 50", "EMA50", ind.EMA50, a.moving_averages.COMPUTE?.EMA50],
    ["SMA 200", "SMA200", ind.SMA200, a.moving_averages.COMPUTE?.SMA200],
    ["Bollinger mid", "BB.middle", ind["BB.middle"], undefined],
  ];
  return (
    <div className="space-y-3 p-4">
      <div className="grid gap-3 sm:grid-cols-3">
        {block(t("ta.summary", "Summary"), a.summary)}
        {block(t("ta.oscillators", "Oscillators"), a.oscillators)}
        {block(t("ta.moving_averages", "Moving averages"), a.moving_averages)}
      </div>
      <div className="grid gap-x-6 sm:grid-cols-2">
        {rows.map(([label, , v, sig]) => (
          <div key={label} className="flex items-center justify-between border-b border-line/60 py-1.5 text-sm">
            <span className="text-muted">{label}</span>
            <span className="flex items-center gap-2">
              <span className="num text-fg">{v === null || v === undefined ? "—" : Math.abs(v) >= 100 ? fmtPrice(v) : v.toFixed(2)}</span>
              {sig && <span className={cn("text-xs", sig === "BUY" ? "text-up" : sig === "SELL" ? "text-down" : "text-muted")}>{sig}</span>}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ symbol picker */

export function SymbolPicker({ value, onChange, quote, className }: { value: string; onChange: (s: string) => void; quote?: string; className?: string }) {
  const t = useT();
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const dq = useDebounced(q, 120);
  const symbols = useSymbols(quote);
  const matches = useMemo(() => {
    const all = symbols.data ?? [];
    const needle = dq.toUpperCase().replace("-", "/");
    const out = needle ? all.filter((s) => s.includes(needle)) : all;
    return out.slice(0, 60);
  }, [symbols.data, dq]);
  return (
    <div className={cn("relative", className)}>
      <button type="button" onClick={() => setOpen((o) => !o)} className="flex h-10 w-full items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 text-sm">
        <CoinIcon symbol={value} size={20} />
        <span className="font-semibold text-fg">{baseOf(value)}</span>
        <span className="text-muted">/{value.split("/")[1]}</span>
      </button>
      {open && (
        <div className="absolute start-0 top-full z-50 mt-1 w-72 rounded-xl border border-line bg-surface p-2 shadow-xl">
          <Input autoFocus value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("market.search_pair", "Search pair…")} />
          <ul className="mt-2 max-h-72 overflow-y-auto">
            {matches.map((s) => (
              <li key={s}>
                <button
                  type="button"
                  onClick={() => {
                    onChange(s);
                    setOpen(false);
                    setQ("");
                  }}
                  className={cn("flex w-full items-center gap-2 rounded-lg px-2 py-1.5 text-sm hover:bg-surface-2", s === value && "bg-surface-2")}
                >
                  <CoinIcon symbol={s} size={18} />
                  {s}
                </button>
              </li>
            ))}
            {!matches.length && <li className="px-2 py-4 text-center text-sm text-muted">{t("palette.empty", "No results")}</li>}
          </ul>
        </div>
      )}
    </div>
  );
}

export const TIMEFRAMES = ["1m", "5m", "15m", "1h", "4h", "1d", "1w"] as const;
