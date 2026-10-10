import { useMemo, useState } from "react";
import { Link, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Bot as BotIcon, Copy, Pencil, Play, Trash2 } from "lucide-react";
import { useT } from "../../i18n";
import { v2 } from "../../lib/api";
import { useCandles } from "../../lib/hooks";
import type { BotDetail as BotDetailT } from "../../lib/types";
import { fmtAmount, fmtDateTime, fmtPct, fmtPrice, fmtUsd, trendClass } from "../../lib/format";
import { cn } from "../../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, ConfirmButton, EmptyState, ErrorState, PageHeader, Segmented, Skeleton, Stat, Switch, Table, Td, Th } from "../../components/ui";
import { PriceChart, type PriceLineSpec } from "../../components/charts";
import { BotStatus, DealBar } from "../../components/trading";
import { TIMEFRAMES } from "../../components/market";
import { useBotActions } from "./Bots";

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/60 py-2 text-sm last:border-0">
      <span className="text-muted">{k}</span>
      <span className="num text-end text-fg">{v}</span>
    </div>
  );
}

export default function BotDetail() {
  const t = useT();
  const { id } = useParams();
  const [tf, setTf] = useState("1h");
  const q = useQuery({ queryKey: ["bot", id], queryFn: () => v2.get<BotDetailT>(`/bots/${id}`), refetchInterval: 8_000 });
  const actions = useBotActions();
  const bot = q.data;
  const candles = useCandles(bot?.symbol ?? "", tf, 300);
  const short = bot?.strategy?.toLowerCase() === "short";

  const lines = useMemo<PriceLineSpec[]>(() => {
    if (!bot || !bot.deal_started) return [];
    const out: PriceLineSpec[] = [
      { price: bot.buy_price, title: t("bots.avg", "Avg"), tone: "info" },
      { price: bot.tp_price, title: "TP", tone: "up" },
    ];
    if (bot.stop_loss || bot.take_profit) out.push({ price: bot.stop_loss_price, title: bot.take_profit ? t("bots.trail", "Trail") : "SL", tone: "down" });
    for (const so of bot.safety_orders) if (so.isOpened && so.price) out.push({ price: so.price, title: "SO", tone: "primary" });
    return out;
  }, [bot, t]);

  if (q.isLoading) return <Skeleton className="h-96" />;
  if (q.error || !bot) return <ErrorState error={q.error ?? t("bots.not_found", "Bot not found")} onRetry={() => q.refetch()} />;

  const unreal = bot.deal_started && bot.buy_price ? ((bot.price_now - bot.buy_price) / bot.buy_price) * 100 * (short ? -1 : 1) : null;
  const deviationSteps = bot.safety_orders.map((_, i) => {
    let cum = 0;
    for (let k = 0; k <= i; k++) cum += (bot.safety_orders_deviation ?? 0) * (bot.safety_orders_deviation_scale ?? 1) ** k;
    return cum;
  });

  return (
    <div className="space-y-5">
      <Link to="/bots" className="inline-flex items-center gap-1 text-sm text-muted hover:text-fg"><ArrowLeft className="size-4 rtl:rotate-180" />{t("nav.bots", "DCA bots")}</Link>
      <PageHeader
        icon={<BotIcon className="size-5" />}
        title={bot.name}
        subtitle={<span className="flex flex-wrap items-center gap-2">{bot.symbol} · <span className="capitalize">{bot.exchange}</span> · <Badge tone={short ? "down" : "up"}>{bot.strategy}</Badge> <BotStatus bot={bot} /></span>}
        actions={
          <>
            <Switch checked={bot.isActive} onChange={(v) => actions.toggle.mutate({ id: bot.id, state: v })} label={bot.isActive ? t("bots.active", "Active") : t("bots.stopped", "Stopped")} />
            {!bot.deal_started && <Button size="sm" variant="secondary" icon={<Play className="size-4" />} onClick={() => actions.run.mutate(bot.id)}>{t("bots.start_deal", "Start a new deal")}</Button>}
            <Link to={`/bots/${bot.id}/edit`}><Button size="sm" variant="secondary" icon={<Pencil className="size-4" />}>{t("common.edit", "Edit")}</Button></Link>
            <Button size="sm" variant="secondary" icon={<Copy className="size-4" />} onClick={() => actions.duplicate.mutate(bot.id)}>{t("bots.duplicate", "Duplicate")}</Button>
            <ConfirmButton title={t("bots.delete_q", "Delete this bot?")} body={bot.deal_started ? t("bots.delete_deal", "The open deal will be closed at market and leftover safety orders cancelled.") : t("bots.delete_idle", "The bot has no open deal; nothing will be sold.")} confirmLabel={t("common.delete", "Delete")} onConfirm={() => actions.remove.mutateAsync(bot.id)}>
              <Trash2 className="size-4" />
            </ConfirmButton>
          </>
        }
      />
      {bot.last_error && <Card className="border-down/40 bg-down-soft p-4 text-sm text-fg">{t("bots.last_error", "Last error")}: {bot.last_error}</Card>}

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Card className="p-4"><Stat label={t("bots.profit", "Realized profit")} value={fmtUsd(bot.total_profit)} tone={trendClass(bot.total_profit)} /></Card>
        <Card className="p-4"><Stat label={t("bots.deals", "Completed deals")} value={bot.total_trades} /></Card>
        <Card className="p-4"><Stat label={t("market.price", "Price")} value={fmtPrice(bot.price_now)} /></Card>
        <Card className="p-4"><Stat label={t("bots.unrealized", "Open P&L")} value={unreal === null ? "—" : fmtPct(unreal)} tone={trendClass(unreal)} /></Card>
        <Card className="p-4"><Stat label={t("bots.position", "Position")} value={bot.deal_started ? fmtAmount(bot.total_volume) : "—"} hint={bot.base_currency} /></Card>
      </div>

      {bot.deal_started && (
        <Card className="p-5">
          <div className="mb-2 flex flex-wrap justify-between gap-2 text-sm">
            <span className="text-muted">{t("bots.deal_since", "Deal open since")} {fmtDateTime(bot.last_open_trade_time)}</span>
            <span className="text-muted">{t("bots.so", "SO")} {bot.safety_orders_filled}/{bot.safety_orders_count} · {t("bots.active_so", "active")} {bot.safety_orders_count_active}</span>
          </div>
          <DealBar sl={bot.stop_loss || bot.take_profit ? bot.stop_loss_price : null} entry={bot.buy_price} price={bot.price_now} tp={bot.tp_price} short={short} />
          <div className="num mt-1 grid grid-cols-2 gap-2 text-xs text-muted sm:grid-cols-4" dir="ltr">
            <span>{t("bots.first_entry", "First entry")} {fmtPrice(bot.deal_start_price)}</span>
            <span>{t("bots.avg", "Avg")} {fmtPrice(bot.buy_price)}</span>
            <span>TP {fmtPrice(bot.tp_price)}</span>
            <span>{bot.take_profit ? t("bots.trail", "Trail") : "SL"} {bot.stop_loss || bot.take_profit ? fmtPrice(bot.stop_loss_price) : "—"}</span>
          </div>
        </Card>
      )}

      <div className="grid gap-5 xl:grid-cols-[1fr_340px]">
        <Card className="min-w-0">
          <CardHeader title={bot.symbol} actions={<Segmented size="xs" value={tf} onChange={setTf} options={TIMEFRAMES.map((v) => ({ value: v, label: v }))} />} />
          <div className="p-2">{candles.data ? <PriceChart candles={candles.data} lines={lines} height={380} /> : <Skeleton className="h-[380px]" />}</div>
        </Card>
        <Card>
          <CardHeader title={t("bots.config", "Configuration")} actions={<Link to={`/bots/${bot.id}/edit`} className="text-xs text-primary hover:underline">{t("common.edit", "Edit")}</Link>} />
          <CardBody className="py-2">
            <Row k={t("bots.order_size", "Order size")} v={`${fmtAmount(bot.amount)} ${bot.base_currency}`} />
            <Row k={t("bots.tp", "Take profit")} v={bot.tp_type === "Percent %" ? `${bot.tp_percent}% (${bot.tp_percent_type === "base" ? t("bots.tp_base_s", "base") : t("bots.tp_volume_s", "avg")})` : t("bots.conditions", "Conditions")} />
            <Row k={t("bots.trailing_tp", "Trailing take profit")} v={bot.trailing_take_profit ? `${bot.trailing_deviation}%` : t("common.off", "Off")} />
            <Row k={t("bots.stop_loss", "Stop loss")} v={bot.stop_loss ? `${bot.stop_loss_price_percent}%${bot.trailing_stop_loss ? ` · ${t("bots.trailing", "trailing")}` : ""}` : t("common.off", "Off")} />
            <Row k={t("bots.safety", "Safety orders")} v={`${bot.safety_orders_count} × ${fmtAmount(bot.safety_orders_size)} (${bot.safety_orders_deviation}% · ${bot.safety_orders_deviation_scale}× · ${bot.safety_orders_size_scale}×)`} />
            <Row k={t("bots.so_active", "Max active at once")} v={bot.safety_orders_count_max_active} />
            <Row k={t("bots.entry_conds", "Deal start conditions")} v={bot.conds?.length ? bot.conds.length : t("bots.asap_s", "ASAP")} />
            <Row k={t("bots.auto_restart", "Start the next deal after take profit")} v={bot.auto_restart ? t("common.on", "On") : t("common.off", "Off")} />
            <Row k={t("bots.cooldown", "Cooldown between deals")} v={bot.cooldown_between_deals ? `${bot.cooldown_between_deals}s` : "—"} />
            <Row k={t("common.created", "Created")} v={fmtDateTime(bot.created_at)} />
          </CardBody>
        </Card>
      </div>

      {!!bot.conds?.length && (
        <Card>
          <CardHeader title={t("bots.entry_conds", "Deal start conditions")} subtitle={t("bots.conds_live", "Latest evaluated values")} />
          <CardBody className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {bot.conds.map((c, i) => (
              <div key={i} className="rounded-xl border border-line p-3 text-sm">
                <p className="font-medium text-fg">{c.indicator}</p>
                <p className="mt-1 text-xs text-muted">{Object.entries(c.conds).map(([k, v]) => `${k}: ${v}`).join(" · ")}</p>
                <p className="num mt-2 text-fg">{t("bots.last_value", "Last value")}: {c.value === undefined || c.value === null ? "—" : typeof c.value === "number" ? c.value.toFixed(2) : c.value}</p>
              </div>
            ))}
          </CardBody>
        </Card>
      )}

      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title={t("bots.safety", "Safety orders")} />
          {bot.safety_orders.length ? (
            <Table>
              <thead><tr><Th>#</Th><Th align="end">{t("bots.dev", "Dev.")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th>{t("order.status", "Status")}</Th></tr></thead>
              <tbody>
                {bot.safety_orders.map((so, i) => (
                  <tr key={so.id}>
                    <Td className="text-muted">{i + 1}</Td>
                    <Td align="end" className="num text-down">-{deviationSteps[i]?.toFixed(2)}%</Td>
                    <Td align="end" className="num">{so.price ? fmtPrice(so.price) : "—"}</Td>
                    <Td align="end" className="num">{so.amount ? fmtAmount(so.amount) : "—"}</Td>
                    <Td><Badge tone={so.isFilled ? "up" : so.isOpened ? "primary" : "neutral"}>{so.isFilled ? t("bots.filled", "Filled") : so.isOpened ? t("bots.placed", "Placed") : t("bots.idle", "Idle")}</Badge></Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : <EmptyState title={t("bots.no_so", "No safety orders configured")} />}
        </Card>
        <Card>
          <CardHeader title={t("bots.trades", "Trade log")} />
          {bot.transactions.length ? (
            <Table>
              <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("order.side", "Side")}</Th><Th align="end">{t("order.price", "Price")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("tx.value", "Value")}</Th></tr></thead>
              <tbody>
                {bot.transactions.map((x) => (
                  <tr key={x.id}>
                    <Td className="text-muted">{fmtDateTime(x.created_at)}</Td>
                    <Td><Badge tone={x.type === "buy" ? "up" : "down"}>{x.type}</Badge>{!x.status && <Badge tone="down" className="ms-1">{t("common.failed", "Failed")}</Badge>}</Td>
                    <Td align="end" className="num">{fmtPrice(x.price)}</Td>
                    <Td align="end" className="num">{fmtAmount(x.amount)}</Td>
                    <Td align="end" className={cn("num", !x.status && "text-down")}>{fmtUsd(x.value)}</Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          ) : <EmptyState title={t("bots.no_trades", "No trades yet")} />}
        </Card>
      </div>
    </div>
  );
}
