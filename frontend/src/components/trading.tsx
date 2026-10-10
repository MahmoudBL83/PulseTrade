import { Link } from "react-router";
import { Bot as BotIcon, Target } from "lucide-react";
import type { Bot, SmartTrade } from "../lib/types";
import { fmtPrice, fmtUsd, trendClass } from "../lib/format";
import { cn } from "../lib/utils";
import { useT } from "../i18n";
import { Badge, Dot } from "./ui";
import { SymbolCell } from "./market";

/** Horizontal SL · entry · price · TP bar (the classic dashboard's deal meter). */
export function DealBar({ sl, entry, price, tp, short }: { sl?: number | null; entry: number; price: number; tp?: number | null; short?: boolean }) {
  const pts = [sl, entry, price, tp].filter((v): v is number => typeof v === "number" && v > 0);
  if (pts.length < 2) return null;
  let lo = Math.min(...pts), hi = Math.max(...pts);
  const pad = (hi - lo) * 0.06 || hi * 0.01;
  lo -= pad;
  hi += pad;
  const pos = (v: number) => `${((v - lo) / (hi - lo)) * 100}%`;
  const winning = short ? price < entry : price > entry;
  return (
    <div className="relative h-7" dir="ltr">
      <div className="absolute inset-x-0 top-3 h-1 rounded-full bg-surface-3" />
      <div
        className={cn("absolute top-3 h-1 rounded-full", winning ? "bg-up" : "bg-down")}
        style={{ left: pos(Math.min(entry, price)), width: `calc(${pos(Math.max(entry, price))} - ${pos(Math.min(entry, price))})` }}
      />
      {sl && sl > 0 && <Marker at={pos(sl)} tone="down" label={`SL ${fmtPrice(sl)}`} />}
      {tp && tp > 0 && <Marker at={pos(tp)} tone="up" label={`TP ${fmtPrice(tp)}`} />}
      <Marker at={pos(entry)} tone="muted" label={`Entry ${fmtPrice(entry)}`} />
      <div className="absolute top-1.5 size-4 -translate-x-1/2 rounded-full border-2 border-surface bg-primary shadow" style={{ left: pos(price) }} title={fmtPrice(price)} />
    </div>
  );
}

function Marker({ at, tone, label }: { at: string; tone: "up" | "down" | "muted"; label: string }) {
  const c = tone === "up" ? "bg-up" : tone === "down" ? "bg-down" : "bg-muted";
  return <div className={cn("absolute top-1.5 h-4 w-0.5 -translate-x-1/2 rounded", c)} style={{ left: at }} title={label} />;
}

export function BotStatus({ bot }: { bot: Bot }) {
  const t = useT();
  if (!bot.isActive) return <Badge><Dot />{t("bots.stopped", "Stopped")}</Badge>;
  if (bot.deal_started) return <Badge tone="up"><Dot tone="up" />{t("bots.in_deal", "In deal")}</Badge>;
  return <Badge tone="info"><Dot tone="info" />{t("bots.waiting", "Waiting")}</Badge>;
}

export function BotRow({ bot }: { bot: Bot }) {
  const t = useT();
  const short = bot.strategy?.toLowerCase() === "short";
  return (
    <Link to={`/bots/${bot.id}`} className="block rounded-xl border border-line p-3 transition-colors hover:border-primary/40 hover:bg-surface-2/40">
      <div className="flex items-center justify-between gap-2">
        <div className="flex min-w-0 items-center gap-2">
          <BotIcon className="size-4 shrink-0 text-muted" />
          <span className="truncate text-sm font-medium text-fg">{bot.name}</span>
        </div>
        <BotStatus bot={bot} />
      </div>
      <div className="mt-2 flex items-center justify-between text-xs text-muted">
        <SymbolCell symbol={bot.symbol} />
        <span className={cn("num", trendClass(bot.total_profit))}>{fmtUsd(bot.total_profit)}</span>
      </div>
      {bot.deal_started && (
        <div className="mt-2">
          <DealBar sl={bot.stop_loss ? bot.stop_loss_price : null} entry={bot.buy_price || bot.deal_start_price} price={bot.price_now} tp={bot.tp_price} short={short} />
          <div className="num flex justify-between text-[11px] text-muted" dir="ltr">
            <span>{t("bots.avg", "Avg")} {fmtPrice(bot.buy_price)}</span>
            <span>{t("bots.so", "SO")} {bot.safety_orders_filled}/{bot.safety_orders_count}</span>
            <span>TP {fmtPrice(bot.tp_price)}</span>
          </div>
        </div>
      )}
    </Link>
  );
}

export function smartSide(st: SmartTrade) {
  return st.trade_type.toLowerCase() === "smart cover" ? "short" : "long";
}

export function smartTarget(st: SmartTrade) {
  const tps = st.take_profit_quantities ?? [];
  const idx = Math.min(st.take_profit_index ?? 0, Math.max(0, tps.length - 1));
  const lvl = tps[idx];
  return lvl ? st.buy_price * (1 + lvl[0] / 100) : null;
}

export function SmartTradeRow({ st }: { st: SmartTrade }) {
  const t = useT();
  const tp = smartTarget(st);
  return (
    <Link to="/smart-trades" className="block rounded-xl border border-line p-3 transition-colors hover:border-primary/40">
      <div className="flex items-center justify-between gap-2">
        <span className="flex items-center gap-2 text-sm font-medium text-fg"><Target className="size-4 text-muted" />{st.symbol}</span>
        <Badge tone={st.isActive ? (st.deal_started ? "up" : "info") : "neutral"}>
          {st.isActive ? (st.deal_started ? t("smart.open", "Open") : t("smart.pending", "Pending")) : t("smart.closed", "Closed")}
        </Badge>
      </div>
      <div className="mt-2 flex justify-between text-xs text-muted">
        <span>{st.trade_type}</span>
        <span className={cn("num", trendClass(st.total_profit))}>{fmtUsd(st.total_profit)}</span>
      </div>
      {st.deal_started && st.buy_price > 0 && (
        <div className="mt-2">
          <DealBar sl={st.stop_loss ? st.stop_loss_price : null} entry={st.buy_price} price={st.price_now || st.last_price || st.buy_price} tp={tp} short={smartSide(st) === "short"} />
        </div>
      )}
    </Link>
  );
}
