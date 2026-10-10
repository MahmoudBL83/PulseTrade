import { useEffect, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot as BotIcon, Sparkles, X } from "lucide-react";
import { useAuth } from "../../context/auth";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { v1, v2 } from "../../lib/api";
import { useTicker } from "../../lib/hooks";
import type { BotDetail, BotTemplate, Condition } from "../../lib/types";
import { fmtPct, fmtPrice } from "../../lib/format";
import { cn, toNumber, useDebounced } from "../../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Field, Input, Notice, PageHeader, Segmented, Select, Skeleton, Switch, Table, Td, Th } from "../../components/ui";
import { SymbolPicker } from "../../components/market";
import { ConditionsBuilder } from "./Conditions";

interface Form {
  name: string;
  pair_type: "single" | "multi";
  symbol: string;
  symbols: string[];
  strategy: "Long" | "Short";
  start_order_type: "Market" | "Limit";
  amount: string;
  amount_type: "1" | "2" | "3";
  tp_type: "Percent %" | "Conditions";
  tp_percent: string;
  tp_percent_type: "base" | "volume";
  trailing_take_profit: boolean;
  trailing_deviation: string;
  min_profit: boolean;
  min_profit_percent: string;
  min_profit_type: "base" | "volume";
  safety_orders_size: string;
  safety_orders_size_type: "1" | "2" | "3";
  safety_orders_count: string;
  safety_orders_count_max_active: string;
  safety_orders_deviation: string;
  safety_orders_deviation_scale: string;
  safety_orders_size_scale: string;
  stop_loss: boolean;
  stop_loss_price_percent: string;
  trailing_stop_loss: boolean;
  stop_loss_time_out: boolean;
  stop_loss_time_out_time: string;
  close_deal_action: "1" | "2";
  Close_deal_after_timeout: boolean;
  timeout: string;
  timeout_type: "1" | "2" | "3";
  cooldown_between_deals: string;
  open_deals_and_stop: string;
  max_price: string;
  min_price: string;
  min_volume: string;
  auto_restart: boolean;
  conds: Condition[];
  tp_conds: Condition[];
}

const DEFAULTS: Form = {
  name: "", pair_type: "single", symbol: "BTC/USDT", symbols: [], strategy: "Long", start_order_type: "Market",
  amount: "50", amount_type: "1", tp_type: "Percent %", tp_percent: "1.8", tp_percent_type: "volume",
  trailing_take_profit: false, trailing_deviation: "0.5", min_profit: false, min_profit_percent: "1", min_profit_type: "volume",
  safety_orders_size: "50", safety_orders_size_type: "1", safety_orders_count: "5", safety_orders_count_max_active: "2",
  safety_orders_deviation: "2", safety_orders_deviation_scale: "1.1", safety_orders_size_scale: "1.5",
  stop_loss: false, stop_loss_price_percent: "8", trailing_stop_loss: false, stop_loss_time_out: false, stop_loss_time_out_time: "60",
  close_deal_action: "1", Close_deal_after_timeout: false, timeout: "24", timeout_type: "1",
  cooldown_between_deals: "", open_deals_and_stop: "", max_price: "", min_price: "", min_volume: "", auto_restart: true,
  conds: [], tp_conds: [],
};

function Section({ title, subtitle, children, aside }: { title: string; subtitle?: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <Card>
      <CardHeader title={title} subtitle={subtitle} actions={aside} />
      <CardBody className="space-y-4">{children}</CardBody>
    </Card>
  );
}

const unitLabel = (type: string, quote: string, base: string) => (type === "1" ? quote : type === "2" ? base : "%");

function fromDetail(b: BotDetail): Form {
  const tt = String(b.timeout_type ?? 1) as Form["timeout_type"];
  const div = tt === "1" ? 3600 : tt === "2" ? 60 : tt === "3" ? 86400 : 1;
  return {
    ...DEFAULTS,
    name: b.name, pair_type: (b.pair_type as Form["pair_type"]) || "single", symbol: b.symbol, symbols: b.symbols ?? [],
    strategy: b.strategy?.toLowerCase() === "short" ? "Short" : "Long",
    start_order_type: b.start_order_type?.toLowerCase() === "limit" ? "Limit" : "Market",
    amount: String(b.amount), amount_type: "2", tp_type: (b.tp_type as Form["tp_type"]) || "Percent %",
    tp_percent: String(b.tp_percent ?? 0), tp_percent_type: (b.tp_percent_type as Form["tp_percent_type"]) || "volume",
    trailing_take_profit: b.trailing_take_profit, trailing_deviation: String(b.trailing_deviation ?? 0),
    min_profit: b.min_profit, min_profit_percent: String(b.min_profit_percent ?? 0), min_profit_type: (b.min_profit_type as Form["min_profit_type"]) || "volume",
    safety_orders_size: String(b.safety_orders_size ?? 0), safety_orders_size_type: "2",
    safety_orders_count: String(b.safety_orders_count ?? 0), safety_orders_count_max_active: String(b.safety_orders_count_max_active ?? 0),
    safety_orders_deviation: String(b.safety_orders_deviation ?? 0), safety_orders_deviation_scale: String(b.safety_orders_deviation_scale ?? 1),
    safety_orders_size_scale: String(b.safety_orders_size_scale ?? 1), stop_loss: b.stop_loss,
    stop_loss_price_percent: String(b.stop_loss_price_percent ?? 0), trailing_stop_loss: b.trailing_stop_loss,
    stop_loss_time_out: b.stop_loss_time_out, stop_loss_time_out_time: String(b.stop_loss_time_out_time ?? 0),
    close_deal_action: String(b.close_deal_action ?? 1) as Form["close_deal_action"], Close_deal_after_timeout: b.Close_deal_after_timeout,
    timeout: String(Math.round(((b.timeout ?? 0) / div) * 100) / 100), timeout_type: tt,
    cooldown_between_deals: b.cooldown_between_deals ? String(b.cooldown_between_deals) : "",
    open_deals_and_stop: b.open_deals_and_stop ? String(b.open_deals_and_stop) : "",
    max_price: b.max_price ? String(b.max_price) : "", min_price: b.min_price ? String(b.min_price) : "",
    min_volume: b.min_volume ? String(b.min_volume) : "", auto_restart: b.auto_restart,
    conds: b.conds ?? [], tp_conds: b.tp_conds ?? [],
  };
}

interface Ladder {
  price: number;
  levels: { index: number; deviation: number; price: number; size: number; total_invested: number; average: number; tp_price: number }[];
  max_capital: number;
  max_deviation: number;
  first_tp: number;
}

export default function BotForm() {
  const t = useT();
  const toast = useToast();
  const nav = useNavigate();
  const qc = useQueryClient();
  const { id } = useParams();
  const editing = !!id;
  const { user } = useAuth();
  const exchange = user?.exchanges.find((e) => e.isActive);
  const [f, setF] = useState<Form>(DEFAULTS);
  const [multiPick, setMultiPick] = useState("ETH/USDT");
  const set = <K extends keyof Form>(k: K, v: Form[K]) => setF((s) => ({ ...s, [k]: v }));

  const templates = useQuery({ queryKey: ["bot-templates"], queryFn: () => v2.get<BotTemplate[]>("/bots/templates"), staleTime: Infinity });
  const existing = useQuery({ queryKey: ["bot", id], queryFn: () => v2.get<BotDetail>(`/bots/${id}`), enabled: editing });
  useEffect(() => {
    if (existing.data) setF(fromDetail(existing.data));
  }, [existing.data]);

  const ticker = useTicker(f.symbol, 10_000);
  const price = ticker.data?.last ?? 0;
  const [base, quote] = f.symbol.split("/");

  // live safety-order ladder preview
  const toQuote = (v: string, type: string) => (type === "1" ? toNumber(v) : type === "2" ? toNumber(v) * price : 0);
  const previewBody = useDebounced(
    JSON.stringify({
      price, amount: toQuote(f.amount, f.amount_type), safety_orders_size: toQuote(f.safety_orders_size, f.safety_orders_size_type),
      safety_orders_count: toNumber(f.safety_orders_count), safety_orders_deviation: toNumber(f.safety_orders_deviation),
      safety_orders_deviation_scale: toNumber(f.safety_orders_deviation_scale, 1), safety_orders_size_scale: toNumber(f.safety_orders_size_scale, 1),
      tp_percent: f.tp_type === "Percent %" ? toNumber(f.tp_percent) : toNumber(f.min_profit_percent), strategy: f.strategy,
    }),
    300,
  );
  const ladder = useQuery({
    queryKey: ["bot-preview", previewBody],
    queryFn: () => v2.post<Ladder>("/bots/preview", JSON.parse(previewBody)),
    enabled: price > 0,
  });

  const applyTemplate = (tpl: BotTemplate) => {
    const s = (k: string) => (tpl[k] === undefined ? undefined : String(tpl[k]));
    setF((cur) => ({
      ...cur,
      name: cur.name || `${tpl.name} · ${cur.symbol}`,
      tp_type: "Percent %",
      tp_percent: s("tp_percent") ?? cur.tp_percent,
      safety_orders_count: s("safety_orders_count") ?? cur.safety_orders_count,
      safety_orders_count_max_active: s("safety_orders_count_max_active") ?? cur.safety_orders_count_max_active,
      safety_orders_deviation: s("safety_orders_deviation") ?? cur.safety_orders_deviation,
      safety_orders_deviation_scale: s("safety_orders_deviation_scale") ?? cur.safety_orders_deviation_scale,
      safety_orders_size_scale: s("safety_orders_size_scale") ?? cur.safety_orders_size_scale,
      stop_loss: Boolean(tpl.stop_loss),
      stop_loss_price_percent: s("stop_loss_price_percent") ?? cur.stop_loss_price_percent,
      trailing_take_profit: Boolean(tpl.trailing_take_profit),
      trailing_deviation: s("trailing_deviation") ?? cur.trailing_deviation,
    }));
    toast.info(t("bots.template_applied", "Template applied"), tpl.description);
  };

  const payload = () => ({
    ...f,
    name: f.name || `${f.strategy} ${f.symbol}`,
    symbols: f.pair_type === "multi" ? f.symbols : [],
    exchange_name: exchange?.name,
    profit_currency: "quote",
    amount: toNumber(f.amount),
    amount_type: Number(f.amount_type),
    tp_percent: toNumber(f.tp_percent),
    trailing_deviation: toNumber(f.trailing_deviation),
    min_profit_percent: toNumber(f.min_profit_percent),
    safety_orders_size: toNumber(f.safety_orders_size),
    safety_orders_size_type: Number(f.safety_orders_size_type),
    safety_orders_count: toNumber(f.safety_orders_count),
    safety_orders_count_max_active: toNumber(f.safety_orders_count_max_active),
    safety_orders_deviation: toNumber(f.safety_orders_deviation),
    safety_orders_deviation_scale: toNumber(f.safety_orders_deviation_scale, 1),
    safety_orders_size_scale: toNumber(f.safety_orders_size_scale, 1),
    stop_loss_price_percent: toNumber(f.stop_loss_price_percent),
    stop_loss_time_out_time: toNumber(f.stop_loss_time_out_time),
    close_deal_action: Number(f.close_deal_action),
    timeout: toNumber(f.timeout),
    timeout_type: Number(f.timeout_type),
    conds: f.conds,
    tp_conds: f.tp_type === "Conditions" ? f.tp_conds : [],
  });

  const save = useMutation({
    mutationFn: () =>
      editing
        ? v1.post<{ message: string }>("/api/v1/edit_bot/", { ...payload(), bot_id: Number(id) })
        : v1.post<{ message: string; bot_id: number }>("/api/v1/create_bot/", payload()),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries({ queryKey: ["bots"] });
      qc.invalidateQueries({ queryKey: ["bot"] });
      const newId = (r as { bot_id?: number }).bot_id;
      nav(editing ? `/bots/${id}` : newId ? `/bots/${newId}` : "/bots");
    },
    onError: (e) => toast.error(e),
  });

  const capital = ladder.data?.max_capital ?? 0;
  const symbolsOk = f.pair_type === "single" ? !!f.symbol : f.symbols.length > 0;
  const invalid = !exchange || !symbolsOk || !toNumber(f.amount) || (f.tp_type === "Percent %" && !toNumber(f.tp_percent));
  const dealLocked = editing && existing.data?.deal_started;

  if (!exchange) {
    return (
      <EmptyState
        icon={<BotIcon className="size-6" />}
        title={t("order.connect", "Connect an exchange or enable paper trading to place orders.")}
        action={<Link to="/exchanges"><Button>{t("dash.onboard_cta", "Connect now")}</Button></Link>}
      />
    );
  }
  if (editing && existing.isLoading) return <Skeleton className="h-96" />;

  return (
    <div className="space-y-5 pb-24">
      <PageHeader
        icon={<BotIcon className="size-5" />}
        title={editing ? t("bots.edit", "Edit bot") : t("bots.new", "New bot")}
        subtitle={t("bots.form_sub", "Runs on {x}. Changes apply from the next evaluation.", { x: exchange.paper ? t("exchanges.paper_long", "Paper trading") : exchange.name })}
      />

      {!editing && (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {(templates.data ?? []).map((tpl) => (
            <button key={tpl.id} type="button" onClick={() => applyTemplate(tpl)} className="rounded-xl border border-line bg-surface p-4 text-start transition-colors hover:border-primary/60">
              <span className="flex items-center gap-2 text-sm font-semibold text-fg"><Sparkles className="size-4 text-primary" />{tpl.name}</span>
              <span className="mt-1 block text-xs text-muted">{tpl.description}</span>
            </button>
          ))}
        </div>
      )}

      <div className="grid gap-5 xl:grid-cols-[1fr_380px]">
        <div className="space-y-5">
          <Section title={t("bots.main", "Main settings")}>
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label={t("bots.name", "Bot name")}><Input value={f.name} maxLength={120} onChange={(e) => set("name", e.target.value)} placeholder={`${f.strategy} ${f.symbol}`} /></Field>
              <Field label={t("bots.strategy", "Strategy")}>
                <Segmented value={f.strategy} onChange={(v) => set("strategy", v)} className={cn("w-full", dealLocked && "pointer-events-none opacity-60")} options={[{ value: "Long", label: t("bots.long", "Long"), tone: "up" }, { value: "Short", label: t("bots.short", "Short"), tone: "down" }]} />
              </Field>
              {!editing && (
                <Field label={t("bots.pairs", "Pairs")}>
                  <Segmented value={f.pair_type} onChange={(v) => set("pair_type", v)} className="w-full" options={[{ value: "single", label: t("bots.single", "Single pair") }, { value: "multi", label: t("bots.multi", "Multi pair") }]} />
                </Field>
              )}
              <Field label={t("market.pair", "Pair")}>
                {f.pair_type === "single" || editing ? (
                  <SymbolPicker value={f.symbol} onChange={(s) => set("symbol", s)} className={dealLocked || editing ? "pointer-events-none opacity-60" : undefined} />
                ) : (
                  <div className="flex gap-2">
                    <SymbolPicker value={multiPick} onChange={setMultiPick} className="flex-1" />
                    <Button variant="secondary" onClick={() => !f.symbols.includes(multiPick) && set("symbols", [...f.symbols, multiPick])}>{t("common.add", "Add")}</Button>
                  </div>
                )}
              </Field>
            </div>
            {f.pair_type === "multi" && !editing && (
              <div className="flex flex-wrap gap-2">
                {f.symbols.map((s) => (
                  <Badge key={s} tone="primary" className="py-1">
                    {s}
                    <button type="button" onClick={() => set("symbols", f.symbols.filter((x) => x !== s))} aria-label={t("common.remove", "Remove")}><X className="size-3" /></button>
                  </Badge>
                ))}
                {!f.symbols.length && <span className="text-xs text-muted">{t("bots.multi_hint", "One bot is created per pair; each counts toward your plan limit.")}</span>}
              </div>
            )}
          </Section>

          <Section title={t("bots.base_order", "Base order")} subtitle={t("bots.base_order_sub", "The first order of every deal.")}>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label={t("bots.order_size", "Order size")}>
                <Input inputMode="decimal" value={f.amount} onChange={(e) => set("amount", e.target.value)} suffix={unitLabel(f.amount_type, quote, base)} />
              </Field>
              <Field label={t("bots.size_in", "Size in")}>
                <Select value={f.amount_type} onChange={(e) => set("amount_type", e.target.value as Form["amount_type"])}>
                  <option value="1">{quote}</option>
                  <option value="2">{base}</option>
                  <option value="3">{t("bots.pct_balance", "% of free {x}", { x: quote })}</option>
                </Select>
              </Field>
              <Field label={t("bots.start_order", "Start order type")}>
                <Segmented value={f.start_order_type} onChange={(v) => set("start_order_type", v)} className="w-full" options={[{ value: "Market", label: t("order.market", "Market") }, { value: "Limit", label: t("order.limit", "Limit") }]} />
              </Field>
            </div>
            {price > 0 && <p className="num text-xs text-muted">{t("bots.price_now", "Current price")}: {fmtPrice(price)} {quote}</p>}
          </Section>

          <Section title={t("bots.tp", "Take profit")}>
            <Segmented value={f.tp_type} onChange={(v) => set("tp_type", v)} options={[{ value: "Percent %", label: t("bots.tp_percent", "Percent") }, { value: "Conditions", label: t("bots.conditions", "Conditions") }]} />
            {f.tp_type === "Percent %" ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("bots.tp_target", "Target profit")}><Input inputMode="decimal" value={f.tp_percent} onChange={(e) => set("tp_percent", e.target.value)} suffix="%" /></Field>
                <Field label={t("bots.tp_from", "Measured from")}>
                  <Select value={f.tp_percent_type} onChange={(e) => set("tp_percent_type", e.target.value as Form["tp_percent_type"])}>
                    <option value="volume">{t("bots.tp_volume", "Average entry (total volume)")}</option>
                    <option value="base">{t("bots.tp_base", "Base order price")}</option>
                  </Select>
                </Field>
                <Switch checked={f.trailing_take_profit} onChange={(v) => set("trailing_take_profit", v)} label={t("bots.trailing_tp", "Trailing take profit")} />
                {f.trailing_take_profit && <Field label={t("bots.trailing_dev", "Trailing deviation")}><Input inputMode="decimal" value={f.trailing_deviation} onChange={(e) => set("trailing_deviation", e.target.value)} suffix="%" /></Field>}
              </div>
            ) : (
              <div className="space-y-4">
                <div className="grid gap-4 sm:grid-cols-2">
                  <Switch checked={f.min_profit} onChange={(v) => set("min_profit", v)} label={t("bots.min_profit", "Require a minimum profit")} />
                  {f.min_profit && <Field label={t("bots.min_profit_pct", "Minimum profit")}><Input inputMode="decimal" value={f.min_profit_percent} onChange={(e) => set("min_profit_percent", e.target.value)} suffix="%" /></Field>}
                </div>
                <ConditionsBuilder value={f.tp_conds} onChange={(c) => set("tp_conds", c)} emptyHint={t("bots.tp_conds_hint", "Close the deal when all of these indicator conditions are true.")} />
              </div>
            )}
          </Section>

          <Section title={t("bots.safety", "Safety orders")} subtitle={t("bots.safety_sub", "Average down (or up for shorts) as price moves against the deal.")}>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label={t("bots.so_size", "Order size")}><Input inputMode="decimal" value={f.safety_orders_size} onChange={(e) => set("safety_orders_size", e.target.value)} suffix={unitLabel(f.safety_orders_size_type, quote, base)} /></Field>
              <Field label={t("bots.size_in", "Size in")}>
                <Select value={f.safety_orders_size_type} onChange={(e) => set("safety_orders_size_type", e.target.value as Form["safety_orders_size_type"])}>
                  <option value="1">{quote}</option>
                  <option value="2">{base}</option>
                  <option value="3">{t("bots.pct_balance", "% of free {x}", { x: quote })}</option>
                </Select>
              </Field>
              <Field label={t("bots.so_count", "Max safety orders")}><Input inputMode="numeric" value={f.safety_orders_count} onChange={(e) => set("safety_orders_count", e.target.value)} /></Field>
              <Field label={t("bots.so_active", "Max active at once")}><Input inputMode="numeric" value={f.safety_orders_count_max_active} onChange={(e) => set("safety_orders_count_max_active", e.target.value)} /></Field>
              <Field label={t("bots.so_dev", "Price deviation")}><Input inputMode="decimal" value={f.safety_orders_deviation} onChange={(e) => set("safety_orders_deviation", e.target.value)} suffix="%" /></Field>
              <Field label={t("bots.so_step", "Step scale")}><Input inputMode="decimal" value={f.safety_orders_deviation_scale} onChange={(e) => set("safety_orders_deviation_scale", e.target.value)} suffix="×" /></Field>
              <Field label={t("bots.so_volume", "Volume scale")}><Input inputMode="decimal" value={f.safety_orders_size_scale} onChange={(e) => set("safety_orders_size_scale", e.target.value)} suffix="×" /></Field>
            </div>
          </Section>

          <Section title={t("bots.stop_loss", "Stop loss")} aside={<Switch checked={f.stop_loss} onChange={(v) => set("stop_loss", v)} />}>
            {f.stop_loss ? (
              <div className="grid gap-4 sm:grid-cols-2">
                <Field label={t("bots.sl_pct", "Stop loss")} hint={t("bots.sl_hint", "From the deal's first entry price.")}><Input inputMode="decimal" value={f.stop_loss_price_percent} onChange={(e) => set("stop_loss_price_percent", e.target.value)} suffix="%" /></Field>
                <Field label={t("bots.sl_action", "After a stop loss")}>
                  <Select value={f.close_deal_action} onChange={(e) => set("close_deal_action", e.target.value as Form["close_deal_action"])}>
                    <option value="1">{t("bots.sl_continue", "Close deal, keep bot running")}</option>
                    <option value="2">{t("bots.sl_stop", "Close deal and stop bot")}</option>
                  </Select>
                </Field>
                <Switch checked={f.trailing_stop_loss} onChange={(v) => set("trailing_stop_loss", v)} label={t("bots.trailing_sl", "Trailing stop loss")} />
                <div className="space-y-2">
                  <Switch checked={f.stop_loss_time_out} onChange={(v) => set("stop_loss_time_out", v)} label={t("bots.sl_timeout", "Only stop out if price stays below for…")} />
                  {f.stop_loss_time_out && <Input inputMode="numeric" value={f.stop_loss_time_out_time} onChange={(e) => set("stop_loss_time_out_time", e.target.value)} suffix={t("common.seconds", "sec")} />}
                </div>
              </div>
            ) : (
              <p className="text-sm text-muted">{t("bots.sl_off", "No stop loss: the deal waits for take profit (classic DCA).")}</p>
            )}
          </Section>

          <Section title={t("bots.entry_conds", "Deal start conditions")} subtitle={t("bots.entry_conds_sub", "Leave empty to open a new deal as soon as possible.")}>
            <ConditionsBuilder value={f.conds} onChange={(c) => set("conds", c)} emptyHint={t("bots.asap", "No conditions — a deal opens immediately.")} />
          </Section>

          <Section title={t("bots.advanced", "Advanced")}>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label={t("bots.min_price", "Only below price")}><Input inputMode="decimal" value={f.max_price} onChange={(e) => set("max_price", e.target.value)} suffix={quote} /></Field>
              <Field label={t("bots.max_price", "Only above price")}><Input inputMode="decimal" value={f.min_price} onChange={(e) => set("min_price", e.target.value)} suffix={quote} /></Field>
              <Field label={t("bots.min_volume", "Min 24h volume")}><Input inputMode="decimal" value={f.min_volume} onChange={(e) => set("min_volume", e.target.value)} suffix={base} /></Field>
              <Field label={t("bots.cooldown", "Cooldown between deals")}><Input inputMode="numeric" value={f.cooldown_between_deals} onChange={(e) => set("cooldown_between_deals", e.target.value)} suffix={t("common.seconds", "sec")} /></Field>
              <Field label={t("bots.max_deals", "Stop after N deals")}><Input inputMode="numeric" value={f.open_deals_and_stop} onChange={(e) => set("open_deals_and_stop", e.target.value)} placeholder="∞" /></Field>
              <div className="flex items-end pb-2"><Switch checked={f.auto_restart} onChange={(v) => set("auto_restart", v)} label={t("bots.auto_restart", "Start the next deal after take profit")} /></div>
            </div>
            <div className="grid gap-4 sm:grid-cols-3">
              <div className="flex items-end pb-2 sm:col-span-1"><Switch checked={f.Close_deal_after_timeout} onChange={(v) => set("Close_deal_after_timeout", v)} label={t("bots.deal_timeout", "Close deals older than")} /></div>
              {f.Close_deal_after_timeout && (
                <>
                  <Field label={t("bots.duration", "Duration")}><Input inputMode="decimal" value={f.timeout} onChange={(e) => set("timeout", e.target.value)} /></Field>
                  <Field label={t("bots.unit", "Unit")}>
                    <Select value={f.timeout_type} onChange={(e) => set("timeout_type", e.target.value as Form["timeout_type"])}>
                      <option value="2">{t("common.minutes", "Minutes")}</option>
                      <option value="1">{t("common.hours", "Hours")}</option>
                      <option value="3">{t("common.days", "Days")}</option>
                    </Select>
                  </Field>
                </>
              )}
            </div>
          </Section>
        </div>

        {/* summary / ladder */}
        <div className="space-y-5 xl:sticky xl:top-20 xl:self-start">
          <Card>
            <CardHeader title={t("bots.preview", "Deal preview")} subtitle={t("bots.preview_sub", "Estimated from the current price.")} />
            <CardBody className="space-y-3">
              <div className="grid grid-cols-2 gap-3 text-sm">
                <div><p className="text-xs text-muted">{t("bots.max_capital", "Max capital per deal")}</p><p className="num font-semibold text-fg">{capital ? `${fmtPrice(capital)} ${quote}` : "—"}</p></div>
                <div><p className="text-xs text-muted">{t("bots.max_dev", "Covers a drop of")}</p><p className="num font-semibold text-fg">{ladder.data ? fmtPct(ladder.data.max_deviation, 2, false) : "—"}</p></div>
                <div><p className="text-xs text-muted">{t("bots.first_tp", "First take profit")}</p><p className="num text-fg">{ladder.data ? fmtPrice(ladder.data.first_tp) : "—"}</p></div>
                <div><p className="text-xs text-muted">{t("bots.so_count", "Max safety orders")}</p><p className="num text-fg">{f.safety_orders_count || 0}</p></div>
              </div>
              {(f.amount_type === "3" || f.safety_orders_size_type === "3") && <Notice>{t("bots.pct_preview", "Sizes in % of balance are resolved when the bot is saved.")}</Notice>}
              {!!ladder.data?.levels.length && (
                <Table className="-mx-4 sm:-mx-5">
                  <thead>
                    <tr>
                      <Th>#</Th>
                      <Th align="end">{t("bots.dev", "Dev.")}</Th>
                      <Th align="end">{t("order.price", "Price")}</Th>
                      <Th align="end">{t("bots.size", "Size")}</Th>
                      <Th align="end">{t("bots.avg", "Avg")}</Th>
                    </tr>
                  </thead>
                  <tbody>
                    {ladder.data.levels.map((l) => (
                      <tr key={l.index}>
                        <Td className="text-muted">{l.index}</Td>
                        <Td align="end" className="num text-down">-{l.deviation.toFixed(2)}%</Td>
                        <Td align="end" className="num">{fmtPrice(l.price)}</Td>
                        <Td align="end" className="num">{fmtPrice(l.size)}</Td>
                        <Td align="end" className="num text-muted">{fmtPrice(l.average)}</Td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              )}
            </CardBody>
          </Card>
          <Notice tone="warning">{t("bots.risk", "Bots trade real funds on live exchanges. Test new settings on the paper exchange or in the backtester first.")}</Notice>
        </div>
      </div>

      <div className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 backdrop-blur lg:start-60">
        <div className="mx-auto flex max-w-[1600px] items-center justify-end gap-2 px-4 py-3 sm:px-6">
          <Link to={editing ? `/bots/${id}` : "/bots"}><Button variant="secondary">{t("common.cancel", "Cancel")}</Button></Link>
          <Link to={`/backtest?symbol=${f.symbol.replace("/", "-")}`}><Button variant="outline">{t("bots.backtest_it", "Backtest these settings")}</Button></Link>
          <Button loading={save.isPending} disabled={invalid} onClick={() => save.mutate()}>{editing ? t("common.save", "Save") : t("bots.create", "Create bot")}</Button>
        </div>
      </div>
    </div>
  );
}
