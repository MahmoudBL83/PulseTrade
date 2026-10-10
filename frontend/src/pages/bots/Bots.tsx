import { useMemo, useState } from "react";
import { Link, useNavigate } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bot as BotIcon, Copy, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { v1, v2 } from "../../lib/api";
import type { Bot } from "../../lib/types";
import { fmtPrice, fmtUsd, timeAgo, trendClass } from "../../lib/format";
import { cn } from "../../lib/utils";
import { Badge, Button, Card, CardBody, ConfirmButton, EmptyState, IconButton, PageHeader, Skeleton, Stat, Switch, Tabs } from "../../components/ui";
import { BotStatus, DealBar } from "../../components/trading";
import { SymbolCell } from "../../components/market";

interface BotsResponse {
  data: Bot[];
  summary: { total: number; active: number; in_deal: number; profit: number; deals: number; limit: number | null };
}

export function useBots() {
  return useQuery({ queryKey: ["bots"], queryFn: () => v2.raw<BotsResponse>("/bots"), refetchInterval: 10_000 });
}

export function useBotActions() {
  const toast = useToast();
  const qc = useQueryClient();
  const nav = useNavigate();
  const done = (r: { message?: string }) => {
    if (r?.message) toast.success(r.message);
    qc.invalidateQueries({ queryKey: ["bots"] });
    qc.invalidateQueries({ queryKey: ["bot"] });
  };
  return {
    toggle: useMutation({ mutationFn: (b: { id: number; state: boolean }) => v1.post<{ message: string }>("/api/v1/toggle_bot", { bot_id: b.id, state: b.state }), onSuccess: done, onError: (e) => toast.error(e) }),
    run: useMutation({ mutationFn: (id: number) => v1.post<{ message: string }>(`/api/v1/run_bot?bot_id=${id}`), onSuccess: done, onError: (e) => toast.error(e) }),
    remove: useMutation({
      mutationFn: (id: number) => v1.post<{ message: string }>("/api/v1/delete_bot", { bot_id: id }),
      onSuccess: (r) => {
        done(r);
        nav("/bots");
      },
      onError: (e) => toast.error(e),
    }),
    duplicate: useMutation({
      mutationFn: (id: number) => v2.post<Bot>(`/bots/${id}/duplicate`),
      onSuccess: (b) => {
        done({ message: `“${b.name}”` });
        nav(`/bots/${b.id}`);
      },
      onError: (e) => toast.error(e),
    }),
  };
}

export default function Bots() {
  const t = useT();
  const bots = useBots();
  const actions = useBotActions();
  const [tab, setTab] = useState<"all" | "active" | "deal" | "stopped">("all");
  const rows = useMemo(() => {
    const all = bots.data?.data ?? [];
    if (tab === "active") return all.filter((b) => b.isActive);
    if (tab === "deal") return all.filter((b) => b.deal_started);
    if (tab === "stopped") return all.filter((b) => !b.isActive);
    return all;
  }, [bots.data, tab]);
  const s = bots.data?.summary;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<BotIcon className="size-5" />}
        title={t("nav.bots", "DCA bots")}
        subtitle={t("bots.subtitle", "Dollar-cost averaging bots with safety orders, trailing exits and indicator conditions.")}
        actions={<Link to="/bots/new"><Button icon={<Plus className="size-4" />}>{t("bots.new", "New bot")}</Button></Link>}
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4"><Stat label={t("bots.total", "Bots")} value={s ? `${s.total}${s.limit && s.limit < 1e8 ? ` / ${s.limit}` : ""}` : "—"} hint={t("bots.plan_limit", "plan limit applies to active bots")} /></Card>
        <Card className="p-4"><Stat label={t("bots.active", "Active")} value={s?.active ?? "—"} hint={t("bots.in_deal_n", "{n} in a deal", { n: s?.in_deal ?? 0 })} /></Card>
        <Card className="p-4"><Stat label={t("bots.deals", "Completed deals")} value={s?.deals ?? "—"} /></Card>
        <Card className="p-4"><Stat label={t("bots.profit", "Realized profit")} value={fmtUsd(s?.profit ?? 0)} tone={trendClass(s?.profit)} /></Card>
      </div>
      <Card>
        <Tabs
          value={tab}
          onChange={setTab}
          className="px-3"
          tabs={[
            { value: "all", label: t("common.all", "All"), count: bots.data?.data.length },
            { value: "active", label: t("bots.active", "Active"), count: s?.active },
            { value: "deal", label: t("bots.in_deal", "In deal"), count: s?.in_deal },
            { value: "stopped", label: t("bots.stopped", "Stopped") },
          ]}
        />
        <CardBody>
          {bots.isLoading && <div className="grid gap-3 md:grid-cols-2">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-40" />)}</div>}
          {bots.data && !rows.length && (
            <EmptyState
              icon={<BotIcon className="size-6" />}
              title={t("bots.none_tab", "No bots here")}
              body={t("bots.none_body", "Create a bot from a template in under a minute — try it on the paper exchange first.")}
              action={<Link to="/bots/new"><Button size="sm">{t("bots.new", "New bot")}</Button></Link>}
            />
          )}
          <div className="grid gap-3 md:grid-cols-2 2xl:grid-cols-3">
            {rows.map((b) => (
              <div key={b.id} className="flex flex-col rounded-xl border border-line p-4">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <Link to={`/bots/${b.id}`} className="block truncate font-semibold text-fg hover:text-primary">{b.name}</Link>
                    <div className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <SymbolCell symbol={b.symbol} />
                      <Badge tone={b.strategy?.toLowerCase() === "short" ? "down" : "up"}>{b.strategy}</Badge>
                      <span className="capitalize">{b.exchange}</span>
                    </div>
                  </div>
                  <Switch checked={b.isActive} onChange={(v) => actions.toggle.mutate({ id: b.id, state: v })} label={<span className="sr-only">{t("bots.toggle", "Active")}</span>} />
                </div>
                <div className="mt-3 flex items-center gap-2"><BotStatus bot={b} />{b.last_error && <Badge tone="down" className="max-w-full truncate" >{b.last_error}</Badge>}</div>
                <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                  <div><p className="text-xs text-muted">{t("bots.profit", "Realized profit")}</p><p className={cn("num", trendClass(b.total_profit))}>{fmtUsd(b.total_profit)}</p></div>
                  <div><p className="text-xs text-muted">{t("bots.deals", "Completed deals")}</p><p className="num text-fg">{b.total_trades}</p></div>
                  <div><p className="text-xs text-muted">{t("bots.tp", "Take profit")}</p><p className="num text-fg">{b.tp_type === "Percent %" ? `${b.tp_percent}%` : t("bots.conditions", "Conditions")}</p></div>
                </div>
                {b.deal_started && (
                  <div className="mt-3">
                    <DealBar sl={b.stop_loss ? b.stop_loss_price : null} entry={b.buy_price || b.deal_start_price} price={b.price_now} tp={b.tp_price} short={b.strategy?.toLowerCase() === "short"} />
                    <div className="num flex justify-between text-[11px] text-muted" dir="ltr">
                      <span>{t("bots.avg", "Avg")} {fmtPrice(b.buy_price)}</span>
                      <span>{fmtPrice(b.price_now)}</span>
                      <span>TP {fmtPrice(b.tp_price)}</span>
                    </div>
                  </div>
                )}
                <div className="mt-auto flex items-center justify-between gap-2 pt-4">
                  <span className="text-xs text-muted">{b.updated_at ? timeAgo(b.updated_at) : ""}</span>
                  <div className="flex items-center gap-1">
                    {!b.deal_started && <IconButton label={t("bots.start_deal", "Start a new deal")} onClick={() => actions.run.mutate(b.id)}><Play className="size-4" /></IconButton>}
                    <Link to={`/bots/${b.id}/edit`}><IconButton label={t("common.edit", "Edit")}><Pencil className="size-4" /></IconButton></Link>
                    <IconButton label={t("bots.duplicate", "Duplicate")} onClick={() => actions.duplicate.mutate(b.id)}><Copy className="size-4" /></IconButton>
                    <ConfirmButton
                      title={t("bots.delete_q", "Delete this bot?")}
                      body={b.deal_started ? t("bots.delete_deal", "The open deal will be closed at market and leftover safety orders cancelled.") : t("bots.delete_idle", "The bot has no open deal; nothing will be sold.")}
                      confirmLabel={t("common.delete", "Delete")}
                      onConfirm={() => actions.remove.mutateAsync(b.id)}
                    >
                      <Trash2 className="size-4" />
                    </ConfirmButton>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
