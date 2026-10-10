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
import { Badge, Button, Card, EmptyState, Input, Notice, PageHeader, Select, Skeleton, Table, Tabs, Td, Th } from "../components/ui";
import { OpenOrdersTable } from "../components/orders";

type Tab = "open" | "orders" | "pulse" | "ledger" | "positions" | "funding";

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
  const q = useHistory<ClosedOrder[]>("orders", "/api/v1/history/orders/", true);
  const [filter, setFilter] = useState("");
  if (q.isLoading) return <Skeleton className="m-4 h-40" />;
  const rows = (q.data ?? []).filter((o) => !filter || o.symbol.includes(filter.toUpperCase()));
  return (
    <>
      <div className="p-4"><Input value={filter} onChange={(e) => setFilter(e.target.value)} placeholder={t("market.search_pair", "Search pair…")} className="max-w-xs" /></div>
      {!rows.length ? <EmptyState title={t("history.no_orders", "No closed or cancelled orders")} /> : (
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
      )}
    </>
  );
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
      {q.isLoading ? <Skeleton className="m-4 h-40" /> : !q.data?.data.length ? <EmptyState title={t("dash.no_activity", "No trades yet")} /> : (
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
            { value: "pulse", label: t("history.pulse", "PulseTrade activity") },
            { value: "ledger", label: t("history.ledger", "Ledger") },
            { value: "positions", label: t("history.positions", "Positions") },
            { value: "funding", label: t("history.funding", "Transfers") },
          ]}
        />
        {tab === "open" && <OpenOrdersTable />}
        {tab === "orders" && <Orders />}
        {tab === "pulse" && <PulseActivity />}
        {tab === "ledger" && <Ledger />}
        {tab === "positions" && <Positions />}
        {tab === "funding" && <Funding />}
      </Card>
      <Notice>{t("history.note", "Exchange history comes straight from each exchange's API; some venues don't offer every report.")}</Notice>
    </div>
  );
}
