import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import { baseOf, fmtAmount, fmtDateTime, fmtPrice, quoteOf } from "../lib/format";
import { cn, toNumber } from "../lib/utils";
import type { PriceAlert } from "../lib/types";
import { Badge, Button, EmptyState, Field, Input, Modal, Segmented, Select, Switch, Table, Td, Th, Notice } from "./ui";

type OrderKind = "market" | "limit" | "cond.limit" | "cond.market";

export function useFreeBalances(exchange?: string | null) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["free-balance", exchange],
    queryFn: () => v1.get<Record<string, number>>("/api/v1/live_balance_json", { exchange: exchange ?? undefined }),
    enabled: !!user?.exchanges.length,
    refetchInterval: 15_000,
  });
}

export function OrderForm({ symbol, price, presetPrice, exchange }: { symbol: string; price?: number; presetPrice?: number | null; exchange?: string | null }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const [side, setSide] = useState<"buy" | "sell">("buy");
  const [kind, setKind] = useState<OrderKind>("limit");
  const [limit, setLimit] = useState("");
  const [trigger, setTrigger] = useState("");
  const [amount, setAmount] = useState("");
  const balances = useFreeBalances(exchange);
  const base = baseOf(symbol), quote = quoteOf(symbol);

  useEffect(() => {
    if (presetPrice) setLimit(String(presetPrice));
  }, [presetPrice]);
  useEffect(() => {
    if (price && !limit) setLimit(String(Number(price.toPrecision(8))));
    // only seed once per symbol
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [symbol, price ? 1 : 0]);
  useEffect(() => {
    setLimit("");
    setAmount("");
    setTrigger("");
  }, [symbol]);

  const px = kind === "market" || kind === "cond.market" ? price ?? 0 : toNumber(limit);
  const qty = toNumber(amount);
  const total = px * qty;
  const freeQuote = balances.data?.[quote] ?? 0;
  const freeBase = balances.data?.[base] ?? 0;

  const pct = (p: number) => {
    if (!px) return;
    const q = side === "buy" ? (freeQuote * p) / px : freeBase * p;
    setAmount(String(Number((q * 0.999).toPrecision(8))));
  };

  const place = useMutation({
    mutationFn: () =>
      v1.post<{ message: string; order: unknown }>("/api/v1/order/", {
        symbol, side, type: kind, amount: qty, order_price: kind.includes("limit") ? toNumber(limit) : 0,
        trigger_price: kind.startsWith("cond.") ? toNumber(trigger) : undefined, exchange: exchange ?? undefined,
      }),
    onSuccess: (r) => {
      toast.success(t("order.placed", "Order placed"), r.message);
      setAmount("");
      qc.invalidateQueries({ queryKey: ["free-balance"] });
      qc.invalidateQueries({ queryKey: ["open-orders"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
    onError: (e) => toast.error(e),
  });

  if (!user) {
    return (
      <EmptyState
        title={t("order.login", "Log in to trade")}
        action={<Link to="/login"><Button size="sm">{t("auth.login", "Log in")}</Button></Link>}
      />
    );
  }
  if (!user.exchanges.length) {
    return (
      <EmptyState
        title={t("order.connect", "Connect an exchange or enable paper trading to place orders.")}
        action={<Link to="/exchanges"><Button size="sm">{t("dash.onboard_cta", "Connect now")}</Button></Link>}
      />
    );
  }

  const invalid = !qty || qty <= 0 || (kind.includes("limit") && !toNumber(limit)) || (kind.startsWith("cond.") && !toNumber(trigger));
  return (
    <form
      className="space-y-3"
      onSubmit={(e) => {
        e.preventDefault();
        if (!invalid) place.mutate();
      }}
    >
      <Segmented value={side} onChange={setSide} className="w-full" options={[{ value: "buy", label: t("order.buy", "Buy"), tone: "up" }, { value: "sell", label: t("order.sell", "Sell"), tone: "down" }]} />
      <Select value={kind} onChange={(e) => setKind(e.target.value as OrderKind)} aria-label={t("order.type", "Order type")}>
        <option value="limit">{t("order.limit", "Limit")}</option>
        <option value="market">{t("order.market", "Market")}</option>
        <option value="cond.limit">{t("order.stop_limit", "Stop-limit (trigger)")}</option>
        <option value="cond.market">{t("order.stop_market", "Stop-market (trigger)")}</option>
      </Select>
      {kind.startsWith("cond.") && (
        <Field label={t("order.trigger", "Trigger price")}>
          <Input inputMode="decimal" value={trigger} onChange={(e) => setTrigger(e.target.value)} suffix={quote} />
        </Field>
      )}
      {kind.includes("limit") && (
        <Field label={t("order.price", "Price")}>
          <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} suffix={quote} />
        </Field>
      )}
      <Field label={t("order.amount", "Amount")}>
        <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} suffix={base} />
      </Field>
      <div className="grid grid-cols-4 gap-1.5">
        {[0.25, 0.5, 0.75, 1].map((p) => (
          <button key={p} type="button" onClick={() => pct(p)} className="rounded-md border border-line py-1 text-xs text-muted hover:border-primary hover:text-fg">
            {p * 100}%
          </button>
        ))}
      </div>
      <div className="space-y-1 rounded-lg bg-surface-2 px-3 py-2 text-xs">
        <div className="flex justify-between"><span className="text-muted">{t("order.available", "Available")}</span><span className="num text-fg">{side === "buy" ? `${fmtAmount(freeQuote)} ${quote}` : `${fmtAmount(freeBase)} ${base}`}</span></div>
        <div className="flex justify-between"><span className="text-muted">{t("order.total", "Total")}</span><span className="num text-fg">{fmtPrice(total)} {quote}</span></div>
      </div>
      <Button type="submit" variant={side === "buy" ? "up" : "down"} className="w-full" loading={place.isPending} disabled={invalid}>
        {side === "buy" ? t("order.buy_x", "Buy {x}", { x: base }) : t("order.sell_x", "Sell {x}", { x: base })}
      </Button>
    </form>
  );
}

interface OpenOrder {
  id: string;
  exchange: string;
  symbol: string;
  filled_amount: number;
  order_type: string;
  total_amount: number;
  remaining_amount: number;
  trigger_price: string;
  order_price: string;
  side: string;
  status: string;
  time: number;
}

export function useOpenOrders(enabled = true) {
  const { user } = useAuth();
  return useQuery({
    queryKey: ["open-orders"],
    queryFn: () => v1.post<OpenOrder[]>("/api/v1/history/open_orders/"),
    enabled: enabled && !!user?.exchanges.length,
    refetchInterval: 15_000,
  });
}

export function OpenOrdersTable({ symbol }: { symbol?: string }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const orders = useOpenOrders();
  const cancel = useMutation({
    mutationFn: (o: OpenOrder) => v1.post<{ message: string }>("/api/v1/order/cancel", { id: o.id, symbol: o.symbol, exchange: o.exchange }),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries({ queryKey: ["open-orders"] });
      qc.invalidateQueries({ queryKey: ["free-balance"] });
    },
    onError: (e) => toast.error(e),
  });
  const rows = useMemo(() => (orders.data ?? []).filter((o) => !symbol || o.symbol === symbol), [orders.data, symbol]);
  if (!rows.length) return <EmptyState title={orders.isLoading ? t("common.loading", "Loading…") : t("order.no_open", "No open orders")} />;
  return (
    <Table>
      <thead>
        <tr>
          <Th>{t("market.time", "Time")}</Th>
          <Th>{t("market.pair", "Pair")}</Th>
          <Th>{t("order.side", "Side")}</Th>
          <Th>{t("order.type", "Type")}</Th>
          <Th align="end">{t("order.price", "Price")}</Th>
          <Th align="end">{t("order.trigger", "Trigger")}</Th>
          <Th align="end">{t("order.amount", "Amount")}</Th>
          <Th align="end">{t("order.filled", "Filled")}</Th>
          <Th align="end" />
        </tr>
      </thead>
      <tbody>
        {rows.map((o) => (
          <tr key={`${o.exchange}-${o.id}`}>
            <Td className="text-muted">{fmtDateTime(o.time)}</Td>
            <Td className="font-medium text-fg">{o.symbol} <span className="text-xs text-muted capitalize">{o.exchange}</span></Td>
            <Td><Badge tone={o.side === "buy" ? "up" : "down"}>{o.side}</Badge></Td>
            <Td className="text-muted">{o.order_type}</Td>
            <Td align="end" className="num">{o.order_price}</Td>
            <Td align="end" className="num text-muted">{o.trigger_price}</Td>
            <Td align="end" className="num">{fmtAmount(o.total_amount)}</Td>
            <Td align="end" className="num text-muted">{fmtAmount(o.filled_amount)}</Td>
            <Td align="end">
              <Button size="xs" variant="outline" loading={cancel.isPending && cancel.variables?.id === o.id} onClick={() => cancel.mutate(o)}>{t("common.cancel", "Cancel")}</Button>
            </Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

/* ------------------------------------------------------------------ alert dialog */

export function AlertModal({ open, onClose, symbol, price, alert }: { open: boolean; onClose: () => void; symbol: string; price?: number; alert?: PriceAlert | null }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [cond, setCond] = useState<PriceAlert["condition"]>("above");
  const [target, setTarget] = useState("");
  const [note, setNote] = useState("");
  const [repeat, setRepeat] = useState(false);
  const [sym, setSym] = useState(symbol);
  useEffect(() => {
    if (!open) return;
    setSym(alert?.symbol ?? symbol);
    setCond(alert?.condition ?? "above");
    setTarget(alert ? String(alert.target) : price ? String(Number((price * 1.05).toPrecision(6))) : "");
    setNote(alert?.note ?? "");
    setRepeat(alert?.repeat ?? false);
  }, [open, alert, symbol, price]);

  const save = useMutation({
    mutationFn: () =>
      alert
        ? v2.patch(`/alerts/${alert.id}`, { target: toNumber(target), note, repeat })
        : v2.post("/alerts", { symbol: sym, condition: cond, target: toNumber(target), note, repeat }),
    onSuccess: () => {
      toast.success(alert ? t("alerts.updated", "Alert updated") : t("alerts.created", "Alert created"));
      qc.invalidateQueries({ queryKey: ["alerts"] });
      onClose();
    },
    onError: (e) => toast.error(e),
  });

  const diff = price && toNumber(target) && cond !== "change_pct" ? ((toNumber(target) - price) / price) * 100 : null;
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={alert ? t("alerts.edit", "Edit alert") : t("alerts.new", "New price alert")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button>
          <Button loading={save.isPending} disabled={!toNumber(target)} onClick={() => save.mutate()}>{t("common.save", "Save")}</Button>
        </>
      }
    >
      <div className="space-y-4">
        <Field label={t("market.pair", "Pair")}>
          <Input value={sym} disabled={!!alert} onChange={(e) => setSym(e.target.value.toUpperCase())} />
        </Field>
        <Field label={t("alerts.condition", "Condition")}>
          <Segmented
            value={cond}
            onChange={setCond}
            className={cn("w-full", alert && "pointer-events-none opacity-60")}
            options={[
              { value: "above", label: t("alerts.above", "Rises above") },
              { value: "below", label: t("alerts.below", "Falls below") },
              { value: "change_pct", label: t("alerts.move", "Moves ±%") },
            ]}
          />
        </Field>
        <Field
          label={cond === "change_pct" ? t("alerts.percent", "Move (%)") : t("alerts.target", "Target price")}
          hint={price ? `${t("alerts.now", "Now")}: ${fmtPrice(price)}${diff !== null ? ` · ${diff > 0 ? "+" : ""}${diff.toFixed(2)}%` : ""}` : undefined}
        >
          <Input inputMode="decimal" value={target} onChange={(e) => setTarget(e.target.value)} suffix={cond === "change_pct" ? "%" : quoteOf(sym)} />
        </Field>
        <Field label={t("alerts.note", "Note (optional)")}>
          <Input value={note} maxLength={255} onChange={(e) => setNote(e.target.value)} />
        </Field>
        <Switch checked={repeat} onChange={setRepeat} label={t("alerts.repeat", "Repeat every time the condition is met again")} />
        <Notice>{t("alerts.channels_hint", "Alerts arrive in-app and on any Discord, Slack or Telegram channel you configured in Settings.")}</Notice>
      </div>
    </Modal>
  );
}
