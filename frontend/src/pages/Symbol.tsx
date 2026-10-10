import { useState } from "react";
import { Link, useParams } from "react-router";
import { ArrowLeftRight, BellPlus, FlaskConical } from "lucide-react";
import { useT } from "../i18n";
import { useAnalysis, useCandles, useOrderBook, useTicker, useTrades } from "../lib/hooks";
import { fmtCompact, fmtPrice, slugToSymbol, symbolToSlug } from "../lib/format";
import { Button, Card, CardHeader, CoinIcon, Segmented, Skeleton, Tabs } from "../components/ui";
import { PriceChart } from "../components/charts";
import { AnalysisPanel, Change, OrderBookView, Price, TIMEFRAMES, TradesTape, WatchStar } from "../components/market";
import { AlertModal, OrderForm } from "../components/orders";
import { useAuth } from "../context/auth";

export default function SymbolPage() {
  const t = useT();
  const { slug = "BTC-USDT" } = useParams();
  const symbol = slugToSymbol(slug);
  const { user } = useAuth();
  const [tf, setTf] = useState<string>("1h");
  const [side, setSide] = useState<"book" | "trades">("book");
  const [taInterval, setTaInterval] = useState("1h");
  const [alertOpen, setAlertOpen] = useState(false);
  const [picked, setPicked] = useState<number | null>(null);
  const ticker = useTicker(symbol);
  const candles = useCandles(symbol, tf, 400);
  const book = useOrderBook(symbol, 14);
  const trades = useTrades(symbol, 30);
  const analysis = useAnalysis(symbol, taInterval);
  const tk = ticker.data;
  const [base, quote] = symbol.split("/");

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-x-8 gap-y-3 p-4">
        <div className="flex items-center gap-3">
          <CoinIcon symbol={symbol} size={36} />
          <div>
            <h1 className="flex items-center gap-1 text-lg font-semibold text-fg">{base}<span className="text-muted">/{quote}</span><WatchStar symbol={symbol} /></h1>
            <p className="text-xs text-muted">{tk?.source === "synthetic" ? t("pulse.demo", "Demo data") : tk?.source}</p>
          </div>
        </div>
        <div>
          <p className="text-2xl font-semibold"><Price value={tk?.last} className="text-fg" /></p>
          <Change value={tk?.percentage} arrow className="text-sm" />
        </div>
        {[
          [t("market.high", "24h high"), fmtPrice(tk?.high)],
          [t("market.low", "24h low"), fmtPrice(tk?.low)],
          [t("market.volume_base", "24h volume ({x})", { x: base }), fmtCompact(tk?.baseVolume)],
          [t("market.volume_quote", "24h volume ({x})", { x: quote }), fmtCompact(tk?.quoteVolume)],
        ].map(([l, v]) => (
          <div key={l} className="hidden sm:block">
            <p className="text-xs text-muted">{l}</p>
            <p className="num text-sm text-fg">{v}</p>
          </div>
        ))}
        <div className="ms-auto flex flex-wrap gap-2">
          {user && <Button variant="secondary" size="sm" icon={<BellPlus className="size-4" />} onClick={() => setAlertOpen(true)}>{t("alerts.set", "Set alert")}</Button>}
          <Link to={`/backtest?symbol=${symbolToSlug(symbol)}`}><Button variant="secondary" size="sm" icon={<FlaskConical className="size-4" />}>{t("nav.backtest", "Backtest")}</Button></Link>
          <Link to={`/trade?symbol=${symbolToSlug(symbol)}`}><Button size="sm" icon={<ArrowLeftRight className="size-4" />}>{t("nav.trade", "Trade")}</Button></Link>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[1fr_320px_300px]">
        <Card className="min-w-0">
          <CardHeader title={t("market.chart", "Chart")} actions={<Segmented size="xs" value={tf} onChange={setTf} options={TIMEFRAMES.map((v) => ({ value: v, label: v }))} />} />
          <div className="p-2">
            {candles.data ? <PriceChart candles={candles.data} height={460} /> : <Skeleton className="h-[460px]" />}
          </div>
        </Card>
        <Card className="min-w-0">
          <Tabs value={side} onChange={setSide} className="px-3" tabs={[{ value: "book", label: t("market.orderbook", "Order book") }, { value: "trades", label: t("market.trades", "Trades") }]} />
          {side === "book" ? <OrderBookView book={book.data} onPick={setPicked} /> : <TradesTape trades={trades.data} />}
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-fg">{t("order.title", "Place order")}</h2>
          <OrderForm symbol={symbol} price={tk?.last} presetPrice={picked} />
        </Card>
      </div>

      <Card>
        <CardHeader
          title={t("ta.title", "Technical analysis")}
          subtitle={t("ta.subtitle", "26 indicators computed from live candles.")}
          actions={<Segmented size="xs" value={taInterval} onChange={setTaInterval} options={["15m", "1h", "4h", "1d", "1w"].map((v) => ({ value: v, label: v }))} />}
        />
        <AnalysisPanel a={analysis.data} />
      </Card>
      <AlertModal open={alertOpen} onClose={() => setAlertOpen(false)} symbol={symbol} price={tk?.last} />
    </div>
  );
}
