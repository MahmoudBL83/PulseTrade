import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Plus, Target, Trash2 } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1 } from "../lib/api";
import { useTicker } from "../lib/hooks";
import type { SmartTrade } from "../lib/types";
import { fmtAmount, fmtDateTime, fmtPct, fmtPrice, fmtUsd, trendClass } from "../lib/format";
import { cn, toNumber } from "../lib/utils";
import { Badge, Button, Card, CardBody, ConfirmButton, EmptyState, Field, Input, Modal, PageHeader, Segmented, Select, Skeleton, Switch, Tabs, Notice } from "../components/ui";
import { DealBar, smartSide, smartTarget } from "../components/trading";
import { SymbolPicker } from "../components/market";
import { useFreeBalances } from "../components/orders";

type Kind = "Smart Trade" | "Smart Cover" | "Smart Buy";
type Entry = "market" | "limit" | "cond.limit" | "cond.market";

interface TpRow { pct: string; qty: string }

function CreateSmartTrade({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { user } = useAuth();
  const exchange = user?.exchanges.find((e) => e.isActive)?.name ?? "";
  const [symbol, setSymbol] = useState("BTC/USDT");
  const ticker = useTicker(symbol, 5000);
  const price = ticker.data?.last ?? 0;
  const balances = useFreeBalances();
  const [kind, setKind] = useState<Kind>("Smart Trade");
  const [entry, setEntry] = useState<Entry>("market");
  const [useAssets, setUseAssets] = useState(false);
  const [limit, setLimit] = useState("");
  const [trigger, setTrigger] = useState("");
  const [amount, setAmount] = useState("");
  const [tpOn, setTpOn] = useState(true);
  const [tps, setTps] = useState<TpRow[]>([{ pct: "3", qty: "50" }, { pct: "6", qty: "50" }]);
  const [tpType, setTpType] = useState<"market" | "limit">("market");
  const [trailTp, setTrailTp] = useState(false);
  const [trailDev, setTrailDev] = useState("1");
  const [slOn, setSlOn] = useState(true);
  const [slPct, setSlPct] = useState("4");
  const [trailSl, setTrailSl] = useState(false);
  const [slTimeout, setSlTimeout] = useState(false);
  const [slTimeoutSec, setSlTimeoutSec] = useState("60");
  const [breakEven, setBreakEven] = useState(true);

  useEffect(() => {
    if (open && price && !limit) setLimit(String(Number(price.toPrecision(8))));
  }, [open, price, limit]);

  const short = kind === "Smart Cover";
  const sign = short ? -1 : 1;
  const ref = entry === "market" || entry === "cond.market" ? price : toNumber(limit) || price;
  const slPrice = ref * (1 - (sign * toNumber(slPct)) / 100);
  const qtySum = tps.reduce((s, r) => s + toNumber(r.qty), 0);
  const base = symbol.split("/")[0], quote = symbol.split("/")[1];
  const freeQuote = balances.data?.[quote] ?? 0;

  const submit = useMutation({
    mutationFn: () =>
      v1.post<{ message: string }>("/api/v1/smart_trades/", {
        trade_type: kind, use_assets: useAssets, symbol, exchange,
        price: entry.includes("limit") ? toNumber(limit) : price, triggerPrice: entry.startsWith("cond.") ? toNumber(trigger) : 0,
        buy_type: entry, amount: toNumber(amount),
        take_profit: tpOn, take_profits: tps.map((r) => [sign * toNumber(r.pct), toNumber(r.qty)]), tpTriggerType: tpType,
        stop_loss: slOn, stop_loss_type: "market", stop_loss_price_percent: -sign * toNumber(slPct), stop_loss_trigger_price: slOn ? slPrice : 0,
        trailing_take_profit: trailTp, trailing_deviation: -sign * toNumber(trailDev), trailing_stop_loss: trailSl,
        stop_loss_time_out: slTimeout, stop_loss_time_out_time: toNumber(slTimeoutSec), move_to_break_even: breakEven,
      }),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries({ queryKey: ["smart-trades"] });
      qc.invalidateQueries({ queryKey: ["free-balance"] });
      onClose();
    },
    onError: (e) => toast.error(e),
  });

  const invalid = !toNumber(amount) || (entry.includes("limit") && !toNumber(limit)) || (entry.startsWith("cond.") && !toNumber(trigger)) || (tpOn && (qtySum <= 0 || qtySum > 100.0001));

  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={t("smart.new", "New smart trade")}
      footer={
        <>
          <Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button>
          <Button loading={submit.isPending} disabled={invalid} onClick={() => submit.mutate()}>{t("smart.create", "Create smart trade")}</Button>
        </>
      }
    >
      <div className="space-y-5">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label={t("market.pair", "Pair")}><SymbolPicker value={symbol} onChange={(s) => { setSymbol(s); setLimit(""); }} /></Field>
          <Field label={t("smart.kind", "Type")}>
            <Select value={kind} onChange={(e) => setKind(e.target.value as Kind)}>
              <option value="Smart Trade">{t("smart.long", "Smart Trade — buy, then take profit (long)")}</option>
              <option value="Smart Cover">{t("smart.short", "Smart Cover — sell, then buy back lower (short)")}</option>
              <option value="Smart Buy">{t("smart.buy_only", "Smart Buy — entry with stop only")}</option>
            </Select>
          </Field>
        </div>

        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-fg">{t("smart.entry", "Entry")}</h3>
          <Switch checked={useAssets} onChange={setUseAssets} label={t("smart.use_assets", "Use coins I already hold (no entry order)")} />
          {!useAssets && (
            <Segmented value={entry} onChange={setEntry} className="w-full" options={[
              { value: "market", label: t("order.market", "Market") },
              { value: "limit", label: t("order.limit", "Limit") },
              { value: "cond.market", label: t("smart.cond_market", "Cond. market") },
              { value: "cond.limit", label: t("smart.cond_limit", "Cond. limit") },
            ]} />
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            {entry.startsWith("cond.") && !useAssets && (
              <Field label={t("order.trigger", "Trigger price")} hint={t("smart.trigger_hint", "Enters when price reaches this level.")}>
                <Input inputMode="decimal" value={trigger} onChange={(e) => setTrigger(e.target.value)} suffix={quote} />
              </Field>
            )}
            {(entry.includes("limit") || useAssets) && (
              <Field label={useAssets ? t("smart.entry_price", "Entry price") : t("order.price", "Price")}>
                <Input inputMode="decimal" value={limit} onChange={(e) => setLimit(e.target.value)} suffix={quote} />
              </Field>
            )}
            <Field label={t("order.amount", "Amount")} hint={`${t("order.available", "Available")}: ${fmtAmount(freeQuote)} ${quote}`}>
              <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} suffix={base} />
            </Field>
          </div>
          {!!toNumber(amount) && <p className="num text-xs text-muted">≈ {fmtPrice(toNumber(amount) * ref)} {quote}</p>}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-fg">{t("smart.take_profit", "Take profit")}</h3>
            <Switch checked={tpOn} onChange={setTpOn} />
          </div>
          {tpOn && (
            <>
              {tps.map((r, i) => (
                <div key={i} className="grid grid-cols-[1fr_1fr_auto_auto] items-end gap-2">
                  <Field label={i === 0 ? t("smart.tp_profit", "Profit %") : undefined}>
                    <Input inputMode="decimal" value={r.pct} onChange={(e) => setTps(tps.map((x, j) => (j === i ? { ...x, pct: e.target.value } : x)))} suffix="%" />
                  </Field>
                  <Field label={i === 0 ? t("smart.tp_qty", "Close % of position") : undefined}>
                    <Input inputMode="decimal" value={r.qty} onChange={(e) => setTps(tps.map((x, j) => (j === i ? { ...x, qty: e.target.value } : x)))} suffix="%" />
                  </Field>
                  <span className="num pb-2.5 text-xs text-muted">{fmtPrice(ref * (1 + (sign * toNumber(r.pct)) / 100))}</span>
                  <Button variant="ghost" size="sm" disabled={tps.length === 1} onClick={() => setTps(tps.filter((_, j) => j !== i))} aria-label={t("common.remove", "Remove")}><Trash2 className="size-4" /></Button>
                </div>
              ))}
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Button variant="outline" size="xs" icon={<Plus className="size-3.5" />} disabled={tps.length >= 5} onClick={() => setTps([...tps, { pct: String(toNumber(tps[tps.length - 1]?.pct) + 3), qty: "0" }])}>
                  {t("smart.add_tp", "Add target")}
                </Button>
                <span className={cn("num text-xs", Math.abs(qtySum - 100) < 0.001 ? "text-muted" : "text-primary")}>{t("smart.qty_total", "Total {n}%", { n: qtySum })}</span>
              </div>
              <div className="grid gap-3 sm:grid-cols-2">
                <Field label={t("smart.tp_order", "Take-profit order")}>
                  <Segmented value={tpType} onChange={setTpType} className="w-full" options={[{ value: "market", label: t("order.market", "Market") }, { value: "limit", label: t("order.limit", "Limit") }]} />
                </Field>
                <div className="space-y-2">
                  <Switch checked={trailTp} onChange={setTrailTp} label={t("smart.trailing_tp", "Trailing on the last target")} />
                  {trailTp && <Input inputMode="decimal" value={trailDev} onChange={(e) => setTrailDev(e.target.value)} suffix={t("smart.deviation", "% deviation")} />}
                </div>
              </div>
            </>
          )}
        </section>

        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-semibold text-fg">{t("smart.stop_loss", "Stop loss")}</h3>
            <Switch checked={slOn} onChange={setSlOn} />
          </div>
          {slOn && (
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label={t("smart.sl_pct", "Loss %")} hint={`${t("smart.stop_at", "Stop at")} ${fmtPrice(slPrice)} ${quote}`}>
                <Input inputMode="decimal" value={slPct} onChange={(e) => setSlPct(e.target.value)} suffix="%" />
              </Field>
              <div className="space-y-2 pt-1">
                <Switch checked={trailSl} onChange={setTrailSl} label={t("smart.trailing_sl", "Trailing stop")} />
                <Switch checked={breakEven} onChange={setBreakEven} label={t("smart.break_even", "Move to break-even after target 1")} />
                <Switch checked={slTimeout} onChange={setSlTimeout} label={t("smart.sl_timeout", "Stop-loss timeout")} />
                {slTimeout && <Input inputMode="numeric" value={slTimeoutSec} onChange={(e) => setSlTimeoutSec(e.target.value)} suffix={t("common.seconds", "sec")} />}
              </div>
            </div>
          )}
        </section>
        {!exchange && <Notice tone="warning">{t("order.connect", "Connect an exchange or enable paper trading to place orders.")}</Notice>}
      </div>
    </Modal>
  );
}

function pnlPct(st: SmartTrade) {
  const px = st.price_now || st.last_price;
  if (!st.deal_started || !st.buy_price || !px) return null;
  return ((px - st.buy_price) / st.buy_price) * 100 * (smartSide(st) === "short" ? -1 : 1);
}

export default function SmartTrades() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [open, setOpen] = useState(false);
  const [tab, setTab] = useState<"active" | "history">("active");
  const list = useQuery({ queryKey: ["smart-trades"], queryFn: () => v1.get<{ smart_trades: SmartTrade[] }>("/api/v1/smart_trades/"), refetchInterval: 10_000 });
  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: "close" | "cancel" | "run" | "open" }) => v1.post<{ message: string }>(`/api/v1/smart_trades/${action}/${id}`),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries({ queryKey: ["smart-trades"] });
      qc.invalidateQueries({ queryKey: ["free-balance"] });
    },
    onError: (e) => toast.error(e),
  });
  const rows = useMemo(() => (list.data?.smart_trades ?? []).filter((s) => (tab === "active" ? s.isActive : !s.isActive)), [list.data, tab]);
  const counts = { active: (list.data?.smart_trades ?? []).filter((s) => s.isActive).length, history: (list.data?.smart_trades ?? []).filter((s) => !s.isActive).length };

  return (
    <div className="space-y-5">
      <PageHeader icon={<Target className="size-5" />} title={t("nav.smart", "Smart trades")} subtitle={t("smart.subtitle", "One position, many exits: staged take profits, stops and trailing.")} actions={<Button icon={<Plus className="size-4" />} onClick={() => setOpen(true)}>{t("smart.new", "New smart trade")}</Button>} />
      <Card>
        <Tabs value={tab} onChange={setTab} className="px-3" tabs={[{ value: "active", label: t("smart.active", "Active"), count: counts.active }, { value: "history", label: t("smart.history", "Finished"), count: counts.history }]} />
        <CardBody className="space-y-3">
          {list.isLoading && <Skeleton className="h-40" />}
          {list.data && !rows.length && <EmptyState icon={<Target className="size-6" />} title={tab === "active" ? t("smart.none", "No open smart trades") : t("smart.no_history", "No finished smart trades yet")} action={tab === "active" && <Button size="sm" onClick={() => setOpen(true)}>{t("smart.new", "New smart trade")}</Button>} />}
          {rows.map((st) => {
            const pnl = pnlPct(st);
            const tp = smartTarget(st);
            return (
              <div key={st.id} className="rounded-xl border border-line p-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex items-center gap-3">
                    <span className="font-semibold text-fg">{st.symbol}</span>
                    <Badge tone={smartSide(st) === "short" ? "down" : "up"}>{st.trade_type}</Badge>
                    <Badge tone={st.isActive ? (st.deal_started ? "up" : "info") : "neutral"}>{st.isActive ? (st.deal_started ? t("smart.open", "Open") : t("smart.pending", "Pending")) : t("smart.closed", "Closed")}</Badge>
                    <span className="text-xs text-muted capitalize">{st.exchange}</span>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    {st.isActive && st.deal_started && (
                      <ConfirmButton variant="secondary" title={t("smart.close_q", "Close this position at market?")} confirmLabel={t("smart.close", "Close at market")} onConfirm={() => act.mutateAsync({ id: st.id, action: "close" })}>
                        {t("smart.close", "Close at market")}
                      </ConfirmButton>
                    )}
                    {!st.isActive && <Button size="sm" variant="secondary" loading={act.isPending && act.variables?.id === st.id} onClick={() => act.mutate({ id: st.id, action: "run" })}>{t("smart.rerun", "Run again")}</Button>}
                    <ConfirmButton title={t("smart.cancel_q", "Cancel and delete this smart trade?")} body={t("smart.cancel_b", "Open entry orders are cancelled; an open position is closed at market.")} confirmLabel={t("common.delete", "Delete")} onConfirm={() => act.mutateAsync({ id: st.id, action: "cancel" })}>
                      <Trash2 className="size-4" />
                    </ConfirmButton>
                  </div>
                </div>
                <div className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-6">
                  <div><p className="text-xs text-muted">{t("smart.entry_price", "Entry price")}</p><p className="num text-fg">{fmtPrice(st.buy_price)}</p></div>
                  <div><p className="text-xs text-muted">{t("market.price", "Price")}</p><p className="num text-fg">{fmtPrice(st.price_now || st.last_price)}</p></div>
                  <div><p className="text-xs text-muted">{t("order.amount", "Amount")}</p><p className="num text-fg">{fmtAmount(st.units)} / {fmtAmount(st.amount)}</p></div>
                  <div><p className="text-xs text-muted">{t("smart.target", "Next target")}</p><p className="num text-fg">{tp ? fmtPrice(tp) : "—"} <span className="text-xs text-muted">({(st.take_profit_index ?? 0) + 1}/{st.take_profit_quantities?.length ?? 0})</span></p></div>
                  <div><p className="text-xs text-muted">{t("smart.stop", "Stop")}</p><p className="num text-fg">{st.stop_loss ? fmtPrice(st.stop_loss_price) : "—"}</p></div>
                  <div><p className="text-xs text-muted">{t("smart.pnl", "P&L")}</p><p className={cn("num", trendClass(pnl ?? st.total_profit))}>{pnl !== null ? fmtPct(pnl) : fmtUsd(st.total_profit)}</p></div>
                </div>
                {st.deal_started && st.buy_price > 0 && (
                  <div className="mt-3"><DealBar sl={st.stop_loss ? st.stop_loss_price : null} entry={st.buy_price} price={st.price_now || st.last_price || st.buy_price} tp={tp} short={smartSide(st) === "short"} /></div>
                )}
                <p className="mt-2 text-xs text-muted">{t("common.created", "Created")} {fmtDateTime(st.created_at)} · {t("smart.realized", "Realized")} <span className={trendClass(st.total_profit)}>{fmtUsd(st.total_profit)}</span></p>
              </div>
            );
          })}
        </CardBody>
      </Card>
      <CreateSmartTrade open={open} onClose={() => setOpen(false)} />
    </div>
  );
}
