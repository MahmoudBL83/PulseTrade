import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Download, History as HistoryIcon } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { download, v1, v2 } from "../lib/api";
import type { Transaction } from "../lib/types";
import { fmtAmount, fmtDateTime, fmtPrice, fmtUsd } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Button, Card, EmptyState, ErrorState, Input, Notice, PageHeader, Select, Skeleton, Table, Tabs, Td, Th } from "../components/ui";
import { OpenOrdersTable, OrderReportStatus } from "../components/orders";
import type { OrderReport } from "../components/orders";

type Tab = "open" | "orders" | "fills" | "pulse" | "ledger" | "positions" | "funding";

interface ClosedOrder {
  id: string; exchange: string; timestamp: number; side: string; order_type: string; order_price: string;
  trigger_price: string; average: number | null; status: string; symbol: string; amount: string; fee: string | number;
}
interface LedgerRow { id: string; exchange: string; timestamp: number; order_type: string; side: string; currency: string; symbol: string; amount: number; fee: string | number; feeCcy: string }
interface Position { symbol?: string; side?: string; contracts?: number; entryPrice?: number; markPrice?: number; unrealizedPnl?: number; leverage?: number; timestamp?: number }
interface TransferRow { id?: string; amount?: number; currency?: string; fromAccount?: string; toAccount?: string; timestamp?: number; status?: string }

function useHistory<T>(key: string, url: string, enabled: boolean) {
  return useQuery({ queryKey: ["history", key], queryFn: () => v1.post<T>(url), enabled, staleTime: 30_000 });
}

function Orders() {
  const t = useT();
  const [draft, setDraft] = useState("");
  const [symbol, setSymbol] = useState("");
  const q = useQuery({ queryKey: ["history", "orders", symbol],
    queryFn: () => v2.raw<OrderReport<ClosedOrder>>("/orders/history", { symbol }), staleTime: 30_000 });
  const rows = q.data?.data ?? [];
  return (
    <>
      <form className="flex flex-wrap gap-2 p-4" onSubmit={(e) => { e.preventDefault(); setSymbol(draft.trim().toUpperCase()); }}>
        <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="BTC/USDT" aria-label={t("history.fetch_pair", "Fetch orders for pair")} className="max-w-xs" />
        <Button type="submit" size="sm" variant="secondary">{t("history.fetch_pair", "Fetch orders for pair")}</Button>
        {symbol && <Button size="sm" variant="outline" onClick={() => { setDraft(""); setSymbol(""); }}>{t("common.all", "All")}</Button>}
      </form>
      <OrderReportStatus sources={q.data?.sources} error={q.error} retry={() => void q.refetch()} />
      {q.isLoading ? <Skeleton className="m-4 h-40" /> : !q.isError && !rows.length ? <EmptyState title={t("history.no_orders", "No closed or cancelled orders")} body={t("history.pair_hint", "Some exchanges require a pair. Enter one above to search its orders.")} /> : rows.length > 0 ? (
        <Table>
          <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("market.pair", "Pair")}</Th><Th>{t("order.side", "Side")}</Th><Th>{t("order.type", "Type")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("order.avg", "Avg fill")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("order.fee", "Fee")}</Th><Th>{t("order.status", "Status")}</Th></tr></thead>
          <tbody>
            {rows.slice(0, 300).map((o) => (
              <tr key={`${o.exchange}-${o.id}`}>
                <Td className="text-muted">{fmtDateTime(o.timestamp)}</Td>
                <Td className="font-medium text-fg">{o.symbol} <span className="text-xs text-muted capitalize">{o.exchange}</span></Td>
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
      ) : null}
    </>
  );
}

interface Fill { id: string; order?: string; exchange: string; symbol: string; timestamp: number; side: string; price: number; amount: number; cost: number; fee?: { cost?: number; currency?: string } }

function Fills() {
  const t = useT();
  const [draft, setDraft] = useState("");
  const [symbol, setSymbol] = useState("");
  const q = useQuery({ queryKey: ["history", "fills", symbol],
    queryFn: () => v2.raw<OrderReport<Fill>>("/orders/fills", { symbol }), staleTime: 30_000 });
  return <>
    <form className="flex flex-wrap gap-2 p-4" onSubmit={(e) => { e.preventDefault(); setSymbol(draft.trim().toUpperCase()); }}>
      <Input value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="BTC/USDT" aria-label={t("history.fetch_pair", "Fetch orders for pair")} className="max-w-xs" />
      <Button type="submit" size="sm" variant="secondary">{t("history.fetch_pair", "Fetch orders for pair")}</Button>
      {symbol && <Button size="sm" variant="outline" onClick={() => { setDraft(""); setSymbol(""); }}>{t("common.all", "All")}</Button>}
    </form>
    <OrderReportStatus sources={q.data?.sources} error={q.error} retry={() => void q.refetch()} />
    {q.isLoading ? <Skeleton className="m-4 h-40" /> : !q.isError && !q.data?.data.length ? <EmptyState title={t("history.no_fills", "No exchange fills found")} body={t("history.pair_hint", "Some exchanges require a pair. Enter one above to search its orders.")} /> : q.data?.data.length ? <Table>
      <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("market.pair", "Pair")}</Th><Th>{t("order.side", "Side")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("tx.value", "Value")}</Th><Th>{t("order.fee", "Fee")}</Th></tr></thead>
      <tbody>{q.data.data.map((fill) => <tr key={`${fill.exchange}-${fill.id}-${fill.order}`}>
        <Td className="text-muted">{fmtDateTime(fill.timestamp)}</Td><Td className="font-medium">{fill.symbol} <span className="text-xs text-muted">{fill.exchange}</span></Td>
        <Td><Badge tone={fill.side === "buy" ? "up" : "down"}>{fill.side}</Badge></Td>
        <Td align="end" className="num">{fmtPrice(fill.price)}</Td><Td align="end" className="num">{fmtAmount(fill.amount)}</Td>
        <Td align="end" className="num">{fmtUsd(fill.cost)}</Td><Td className="text-muted">{fill.fee?.cost ?? "—"} {fill.fee?.currency}</Td>
      </tr>)}</tbody>
    </Table> : null}
  </>;
}

function PulseActivity() {
  const t = useT();
  const toast = useToast();
  const [type, setType] = useState("");
  const [symbol, setSymbol] = useState("");
  const [page, setPage] = useState(0);
  const limit = 50;
  const q = useQuery({
    queryKey: ["transactions", type, symbol, page],
    queryFn: () => v2.raw<{ data: Transaction[]; total: number }>("/transactions", { limit, offset: page * limit, type, symbol: symbol ? symbol.toUpperCase() : undefined }),
    placeholderData: (prev) => prev,
  });
  const total = q.data?.total ?? 0;
  return (
    <>
      <div className="flex flex-wrap items-center gap-2 p-4">
        <Select value={type} onChange={(e) => { setType(e.target.value); setPage(0); }} className="w-32">
          <option value="">{t("common.all", "All")}</option>
          <option value="buy">{t("order.buy", "Buy")}</option>
          <option value="sell">{t("order.sell", "Sell")}</option>
        </Select>
        <Input value={symbol} onChange={(e) => { setSymbol(e.target.value); setPage(0); }} placeholder="BTC/USDT" className="w-40" />
        <Button size="sm" variant="secondary" className="ms-auto" icon={<Download className="size-4" />} onClick={() => download("/api/v2/export/transactions.csv", "pulsetrade-transactions.csv").catch((e) => toast.error(e))}>
          {t("history.export", "Export CSV")}
        </Button>
      </div>
      {q.isLoading ? <Skeleton className="m-4 h-40" /> : q.isError ? <ErrorState error={q.error} onRetry={() => void q.refetch()} /> : !q.data?.data.length ? <EmptyState title={t("dash.no_activity", "No trades yet")} /> : (
        <>
          <Table>
            <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("market.pair", "Pair")}</Th><Th>{t("order.side", "Side")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("tx.value", "Value")}</Th><Th>{t("history.source", "Source")}</Th><Th>{t("order.status", "Status")}</Th></tr></thead>
            <tbody>
              {q.data.data.map((x) => (
                <tr key={x.id}>
                  <Td className="text-muted">{fmtDateTime(x.created_at)}</Td>
                  <Td className="font-medium text-fg">{x.symbol} <span className="text-xs text-muted capitalize">{x.exchange}</span></Td>
                  <Td><Badge tone={x.type === "buy" ? "up" : "down"}>{x.type}</Badge></Td>
                  <Td align="end" className="num">{fmtPrice(x.price)}</Td>
                  <Td align="end" className="num">{fmtAmount(x.amount)}</Td>
                  <Td align="end" className="num">{fmtUsd(x.value)}</Td>
                  <Td className="text-xs text-muted">{x.bot_id ? <Link className="text-primary hover:underline" to={`/bots/${x.bot_id}`}>{t("history.bot", "Bot #{n}", { n: x.bot_id })}</Link> : x.sma_id ? t("history.smart", "Smart trade #{n}", { n: x.sma_id }) : t("history.manual", "Manual")}</Td>
                  <Td>{x.status ? <Badge tone="up">{t("common.ok", "OK")}</Badge> : <Badge tone="down" className="max-w-56 truncate">{typeof x.err_msg === "string" && x.err_msg ? x.err_msg : t("common.failed", "Failed")}</Badge>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
          <div className="flex items-center justify-between p-4 text-sm text-muted">
            <span className="num">{page * limit + 1}–{Math.min(total, (page + 1) * limit)} / {total}</span>
            <div className="flex gap-2">
              <Button size="sm" variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>{t("common.prev", "Previous")}</Button>
              <Button size="sm" variant="secondary" disabled={(page + 1) * limit >= total} onClick={() => setPage(page + 1)}>{t("common.next", "Next")}</Button>
            </div>
          </div>
        </>
      )}
    </>
  );
}

function Ledger() {
  const t = useT();
  const q = useHistory<LedgerRow[]>("ledger", "/api/v1/history/trades/", true);
  if (q.isLoading) return <Skeleton className="m-4 h-40" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length) return <EmptyState title={t("history.no_ledger", "No ledger entries (or this exchange does not provide them)")} />;
  return (
    <Table>
      <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("history.kind", "Kind")}</Th><Th>{t("order.side", "Side")}</Th><Th>{t("wallet.coin", "Coin")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("order.fee", "Fee")}</Th><Th>{t("exchanges.exchange", "Exchange")}</Th></tr></thead>
      <tbody>
        {q.data.slice(0, 300).map((r, i) => (
          <tr key={`${r.exchange}-${r.id}-${i}`}>
            <Td className="text-muted">{fmtDateTime(r.timestamp)}</Td>
            <Td className="text-muted">{r.order_type}</Td>
            <Td><Badge tone={r.side === "Buy" ? "up" : "down"}>{r.side}</Badge></Td>
            <Td className="font-medium">{r.currency}</Td>
            <Td align="end" className="num">{fmtAmount(r.amount)}</Td>
            <Td align="end" className="num text-muted">{String(r.fee)} {r.feeCcy !== "-" ? r.feeCcy : ""}</Td>
            <Td className="text-muted capitalize">{r.exchange}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Positions() {
  const t = useT();
  const q = useHistory<Position[]>("positions", "/api/v1/history/positions_history/", true);
  if (q.isLoading) return <Skeleton className="m-4 h-40" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length) return <EmptyState title={t("history.no_positions", "No open derivative positions")} />;
  return (
    <Table>
      <thead><tr><Th>{t("market.pair", "Pair")}</Th><Th>{t("order.side", "Side")}</Th><Th align="end">{t("history.contracts", "Size")}</Th><Th align="end">{t("bt.entry", "Entry")}</Th><Th align="end">{t("history.mark", "Mark")}</Th><Th align="end">{t("history.upnl", "Unrealized P&L")}</Th><Th align="end">{t("history.leverage", "Leverage")}</Th></tr></thead>
      <tbody>
        {q.data.map((p, i) => (
          <tr key={i}>
            <Td className="font-medium">{p.symbol}</Td>
            <Td><Badge tone={p.side === "long" ? "up" : "down"}>{p.side}</Badge></Td>
            <Td align="end" className="num">{fmtAmount(p.contracts)}</Td>
            <Td align="end" className="num">{fmtPrice(p.entryPrice)}</Td>
            <Td align="end" className="num">{fmtPrice(p.markPrice)}</Td>
            <Td align="end" className={cn("num", (p.unrealizedPnl ?? 0) >= 0 ? "text-up" : "text-down")}>{fmtUsd(p.unrealizedPnl)}</Td>
            <Td align="end" className="num">{p.leverage ? `${p.leverage}×` : "—"}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Funding() {
  const t = useT();
  const q = useHistory<TransferRow[]>("funding", "/api/v1/history/funding_history/", true);
  if (q.isLoading) return <Skeleton className="m-4 h-40" />;
  if (q.isError) return <ErrorState error={q.error} onRetry={() => void q.refetch()} />;
  if (!q.data?.length) return <EmptyState title={t("wallet.no_transfers", "No transfers yet")} />;
  return (
    <Table>
      <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("wallet.coin", "Coin")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th>{t("wallet.from", "From")}</Th><Th>{t("wallet.to", "To")}</Th><Th>{t("order.status", "Status")}</Th></tr></thead>
      <tbody>
        {q.data.map((r, i) => (
          <tr key={r.id ?? i}>
            <Td className="text-muted">{fmtDateTime(r.timestamp)}</Td>
            <Td className="font-medium">{r.currency}</Td>
            <Td align="end" className="num">{fmtAmount(r.amount)}</Td>
            <Td className="text-muted">{r.fromAccount}</Td>
            <Td className="text-muted">{r.toAccount}</Td>
            <Td><Badge>{r.status ?? "—"}</Badge></Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

export default function History() {
  const t = useT();
  const { user } = useAuth();
  const [tab, setTab] = useState<Tab>("open");
  if (!user?.exchanges.length) {
    return (
      <>
        <PageHeader icon={<HistoryIcon className="size-5" />} title={t("nav.history", "History")} />
        <Card><EmptyState title={t("dash.onboard_title", "Connect an exchange to get started")} action={<Link to="/exchanges"><Button>{t("dash.onboard_cta", "Connect now")}</Button></Link>} /></Card>
      </>
    );
  }
  return (
    <div className="space-y-5">
      <PageHeader icon={<HistoryIcon className="size-5" />} title={t("nav.history", "History")} subtitle={t("history.subtitle", "Orders and account movements across all connected exchanges.")} />
      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          className="px-3"
          tabs={[
            { value: "open", label: t("order.open", "Open orders") },
            { value: "orders", label: t("order.history", "Order history") },
            { value: "fills", label: t("history.fills", "Exchange fills") },
            { value: "pulse", label: t("history.pulse", "PulseTrade activity") },
            { value: "ledger", label: t("history.ledger", "Ledger") },
            { value: "positions", label: t("history.positions", "Positions") },
            { value: "funding", label: t("history.funding", "Transfers") },
          ]}
        />
        {tab === "open" && <OpenOrdersTable />}
        {tab === "orders" && <Orders />}
        {tab === "fills" && <Fills />}
        {tab === "pulse" && <PulseActivity />}
        {tab === "ledger" && <Ledger />}
        {tab === "positions" && <Positions />}
        {tab === "funding" && <Funding />}
      </Card>
      <Notice>{t("history.note", "Exchange history comes straight from each exchange's API; some venues don't offer every report.")}</Notice>
    </div>
  );
}
