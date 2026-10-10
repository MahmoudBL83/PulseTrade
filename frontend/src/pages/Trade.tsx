import { useState } from "react";
import { useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../context/auth";
import { useT } from "../i18n";
import { v1 } from "../lib/api";
import { useCandles, useOrderBook, useTicker, useTrades } from "../lib/hooks";
import { fmtAmount, fmtDateTime, fmtPrice, slugToSymbol, symbolToSlug } from "../lib/format";
import { Badge, Card, CardHeader, EmptyState, Segmented, Skeleton, Table, Tabs, Td, Th } from "../components/ui";
import { PriceChart } from "../components/charts";
import { Change, OrderBookView, Price, SymbolPicker, TIMEFRAMES, TradesTape } from "../components/market";
import { OpenOrdersTable, OrderForm, useFreeBalances } from "../components/orders";

interface ClosedOrder {
  id: string;
  exchange: string;
  datetime: string;
  timestamp: number;
  side: string;
  order_type: string;
  order_price: string;
  average: number | null;
  status: string;
  symbol: string;
  amount: string;
  fee: string | number;
}

function OrderHistory({ symbol }: { symbol: string }) {
  const t = useT();
  const q = useQuery({ queryKey: ["order-history"], queryFn: () => v1.post<ClosedOrder[]>("/api/v1/history/orders/"), refetchInterval: 30_000 });
  const rows = (q.data ?? []).filter((o) => o.symbol === symbol).slice(0, 50);
  if (q.isLoading) return <Skeleton className="m-4 h-32" />;
  if (!rows.length) return <EmptyState title={t("order.no_history", "No orders for this pair yet")} />;
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t("market.time", "Time")}</Th>
          <Th>{t("order.side", "Side")}</Th>
          <Th>{t("order.type", "Type")}</Th>
          <Th align="end">{t("order.price", "Price")}</Th>
          <Th align="end">{t("order.avg", "Avg fill")}</Th>
          <Th align="end">{t("order.amount", "Amount")}</Th>
          <Th align="end">{t("order.fee", "Fee")}</Th>
          <Th>{t("order.status", "Status")}</Th>
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={`${o.exchange}-${o.id}`}>
            <Td className="text-muted">{fmtDateTime(o.timestamp)}</Td>
            <Td><Badge tone={o.side === "buy" ? "up" : "down"}>{o.side}</Badge></Td>
            <Td className="text-muted">{o.order_type}</Td>
            <Td align="end" className="num">{o.order_price}</Td>
            <Td align="end" className="num">{fmtPrice(o.average)}</Td>
            <Td align="end" className="num">{o.amount}</Td>
            <Td align="end" className="num text-muted">{String(o.fee)}</Td>
            <Td><Badge tone={o.status === "closed" ? "up" : "neutral"}>{o.status}</Badge></Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Balances() {
  const t = useT();
  const b = useFreeBalances();
  const rows = Object.entries(b.data ?? {}).filter(([, v]) => v > 0).sort((a, z) => z[1] - a[1]);
  if (!rows.length) return <EmptyState title={t("trade.no_balance", "No free balances")} />;
  return (
    <div className="grid gap-2 p-4 sm:grid-cols-3 lg:grid-cols-6">
      {rows.map(([c, v]) => (
        <div key={c} className="rounded-lg border border-line px-3 py-2">
          <p className="text-xs text-muted">{c}</p>
          <p className="num text-sm text-fg">{fmtAmount(v)}</p>
        </div>
      ))}
    </div>
  );
}

export default function Trade() {
  const t = useT();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const symbol = slugToSymbol(params.get("symbol") ?? "BTC-USDT");
  const [tf, setTf] = useState("15m");
  const [panel, setPanel] = useState<"book" | "trades">("book");
  const [bottom, setBottom] = useState<"open" | "history" | "balances">("open");
  const [picked, setPicked] = useState<number | null>(null);
  const ticker = useTicker(symbol, 3000);
  const candles = useCandles(symbol, tf, 300);
  const book = useOrderBook(symbol, 16);
  const trades = useTrades(symbol, 30);
  const active = user?.exchanges.find((e) => e.isActive);

  return (
    <div className="space-y-4">
      <Card className="flex flex-wrap items-center gap-x-6 gap-y-3 p-3">
        <SymbolPicker value={symbol} onChange={(s) => setParams({ symbol: symbolToSlug(s) })} className="w-44" />
        <div>
          <p className="text-xl font-semibold"><Price value={ticker.data?.last} className="text-fg" /></p>
          <Change value={ticker.data?.percentage} className="text-xs" />
        </div>
        <div className="hidden text-xs sm:block"><p className="text-muted">{t("market.high", "24h high")}</p><p className="num text-fg">{fmtPrice(ticker.data?.high)}</p></div>
        <div className="hidden text-xs sm:block"><p className="text-muted">{t("market.low", "24h low")}</p><p className="num text-fg">{fmtPrice(ticker.data?.low)}</p></div>
        {active && <Badge tone={active.paper ? "info" : "primary"} className="ms-auto capitalize">{active.paper ? t("exchanges.paper_long", "Paper trading") : active.name}</Badge>}
      </Card>
      <div className="grid gap-4 xl:grid-cols-[1fr_300px_300px]">
        <Card className="min-w-0">
          <CardHeader title={symbol} actions={<Segmented size="xs" value={tf} onChange={setTf} options={TIMEFRAMES.map((v) => ({ value: v, label: v }))} />} />
          <div className="p-2">{candles.data ? <PriceChart candles={candles.data} height={480} /> : <Skeleton className="h-[480px]" />}</div>
        </Card>
        <Card className="min-w-0">
          <Tabs value={panel} onChange={setPanel} className="px-3" tabs={[{ value: "book", label: t("market.orderbook", "Order book") }, { value: "trades", label: t("market.trades", "Trades") }]} />
          {panel === "book" ? <OrderBookView book={book.data} onPick={setPicked} rows={14} /> : <TradesTape trades={trades.data} />}
        </Card>
        <Card className="p-4">
          <h2 className="mb-3 text-sm font-semibold text-fg">{t("order.title", "Place order")}</h2>
          <OrderForm symbol={symbol} price={ticker.data?.last} presetPrice={picked} />
        </Card>
      </div>
      <Card>
        <Tabs
          value={bottom}
          onChange={setBottom}
          className="px-3"
          tabs={[
            { value: "open", label: t("order.open", "Open orders") },
            { value: "history", label: t("order.history", "Order history") },
            { value: "balances", label: t("trade.balances", "Balances") },
          ]}
        />
        {bottom === "open" && <OpenOrdersTable />}
        {bottom === "history" && <OrderHistory symbol={symbol} />}
        {bottom === "balances" && <Balances />}
      </Card>
    </div>
  );
}
