import { useMemo } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Activity, Bot, LayoutDashboard, LifeBuoy, Users } from "lucide-react";
import { useT } from "../../i18n";
import { v2 } from "../../lib/api";
import { fmtCompact, fmtNum, fmtPct, fmtUsd, toDate } from "../../lib/format";
import { Card, CardBody, CardHeader, ErrorState, PageHeader, Skeleton, Stat } from "../../components/ui";
import { AreaChart, Donut, donutColor } from "../../components/charts";

interface Point { id: number; timestamp: string | null; count?: number; value?: number }
export interface AdminStats {
  users: number; new_users_7d: number; bots_active: number; bots_total: number; smart_trades_active: number;
  paper_accounts: number; alerts_active: number; transactions: number; buys: number; sells: number;
  volume_24h: number; open_tickets: number; plans: { id: number; type: string; users: number }[];
  users_history: Point[]; bots_history: Point[]; volume_history: Point[];
}

const series = (rows: Point[], key: "count" | "value") =>
  rows.flatMap((r) => {
    const d = toDate(r.timestamp);
    return d ? [{ t: d.getTime(), v: Number(r[key] ?? 0) }] : [];
  });
const intFormat = (v: number) => fmtNum(v, 0);
const usdFormat = (v: number) => fmtCompact(v, "$");

export default function AdminOverview() {
  const t = useT();
  const q = useQuery({ queryKey: ["admin", "stats"], queryFn: () => v2.get<AdminStats>("/admin/stats"), refetchInterval: 60_000 });
  const s = q.data;
  const users = useMemo(() => series(s?.users_history ?? [], "count"), [s]);
  const bots = useMemo(() => series(s?.bots_history ?? [], "count"), [s]);
  const volume = useMemo(() => series(s?.volume_history ?? [], "value"), [s]);

  if (q.isError) return <Card><ErrorState error={q.error} onRetry={() => q.refetch()} /></Card>;
  return (
    <div className="space-y-5">
      <PageHeader icon={<LayoutDashboard className="size-5" />} title={t("admin.overview", "Overview")} subtitle={t("admin.overview_sub", "Platform health at a glance.")} />
      {!s ? <Skeleton className="h-96" /> : (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-6">
            <Card className="p-4"><Stat label={t("admin.users", "Users")} value={fmtNum(s.users, 0)} hint={t("admin.new7", "+{n} this week", { n: s.new_users_7d })} /></Card>
            <Card className="p-4"><Stat label={t("admin.bots_active", "Active bots")} value={fmtNum(s.bots_active, 0)} hint={t("admin.of_total", "of {n}", { n: s.bots_total })} /></Card>
            <Card className="p-4"><Stat label={t("admin.smart_active", "Active smart trades")} value={fmtNum(s.smart_trades_active, 0)} /></Card>
            <Card className="p-4"><Stat label={t("admin.volume24", "Volume 24h")} value={fmtUsd(s.volume_24h, 0)} /></Card>
            <Card className="p-4"><Stat label={t("admin.paper", "Paper accounts")} value={fmtNum(s.paper_accounts, 0)} hint={t("admin.alerts_n", "{n} active alerts", { n: s.alerts_active })} /></Card>
            <Link to="/admin/support">
              <Card className="h-full p-4 transition-colors hover:border-primary/60">
                <Stat label={t("admin.tickets", "Tickets awaiting reply")} value={s.open_tickets} tone={s.open_tickets ? "text-primary" : undefined} />
              </Card>
            </Link>
          </div>
          <div className="grid gap-5 xl:grid-cols-3">
            <Card className="xl:col-span-2">
              <CardHeader title={<span className="flex items-center gap-2"><Users className="size-4 text-primary" />{t("admin.users_growth", "Registered users")}</span>} />
              <CardBody className="pt-2">{users.length > 1 ? <AreaChart points={users} height={240} valueFormat={intFormat} /> : <p className="py-16 text-center text-sm text-muted">{t("admin.no_history", "History is recorded daily by the scheduler.")}</p>}</CardBody>
            </Card>
            <Card>
              <CardHeader title={t("admin.plan_mix", "Users by plan")} />
              <CardBody className="flex flex-col items-center gap-4">
                <Donut items={s.plans.map((p) => ({ label: p.type, value: p.users }))} center={<><span className="num text-xl font-semibold text-fg">{s.users}</span><span className="text-xs text-muted">{t("admin.users", "Users")}</span></>} />
                <ul className="w-full space-y-1.5 text-sm">
                  {s.plans.map((p, i) => (
                    <li key={p.id} className="flex items-center justify-between">
                      <span className="flex items-center gap-2 capitalize text-fg"><span className="size-2.5 rounded-full" style={{ background: donutColor(i) }} />{p.type}</span>
                      <span className="num text-muted">{p.users} · {fmtPct(s.users ? (p.users / s.users) * 100 : 0, 0, false)}</span>
                    </li>
                  ))}
                </ul>
              </CardBody>
            </Card>
          </div>
          <div className="grid gap-5 lg:grid-cols-2">
            <Card>
              <CardHeader title={<span className="flex items-center gap-2"><Bot className="size-4 text-info" />{t("admin.bots_hist", "Active bots")}</span>} />
              <CardBody className="pt-2">{bots.length > 1 ? <AreaChart points={bots} height={200} tone="info" valueFormat={intFormat} /> : <p className="py-12 text-center text-sm text-muted">{t("admin.no_history", "History is recorded daily by the scheduler.")}</p>}</CardBody>
            </Card>
            <Card>
              <CardHeader
                title={<span className="flex items-center gap-2"><Activity className="size-4 text-up" />{t("admin.volume_hist", "Daily volume")}</span>}
                subtitle={t("admin.trades_split", "{n} trades · {b} buys / {s} sells", { n: fmtNum(s.transactions, 0), b: fmtNum(s.buys, 0), s: fmtNum(s.sells, 0) })}
              />
              <CardBody className="pt-2">{volume.length > 1 ? <AreaChart points={volume} height={200} tone="up" valueFormat={usdFormat} /> : <p className="py-12 text-center text-sm text-muted">{t("admin.no_history", "History is recorded daily by the scheduler.")}</p>}</CardBody>
            </Card>
          </div>
          {s.open_tickets > 0 && (
            <Link to="/admin/support" className="flex items-center gap-2 text-sm text-primary hover:underline"><LifeBuoy className="size-4" />{t("admin.go_support", "Answer {n} waiting ticket(s)", { n: s.open_tickets })}</Link>
          )}
        </>
      )}
    </div>
  );
}
