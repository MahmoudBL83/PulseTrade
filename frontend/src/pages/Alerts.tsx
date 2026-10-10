import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BellRing, Pencil, Plus, Repeat, Trash2 } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import type { PriceAlert } from "../lib/types";
import { fmtPrice, symbolToSlug, timeAgo } from "../lib/format";
import { Badge, Button, Card, EmptyState, IconButton, Notice, PageHeader, Skeleton, Switch, Table, Td, Th } from "../components/ui";
import { AlertModal } from "../components/orders";

export default function Alerts() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [modal, setModal] = useState<{ open: boolean; alert: PriceAlert | null }>({ open: false, alert: null });
  const list = useQuery({ queryKey: ["alerts"], queryFn: () => v2.get<PriceAlert[]>("/alerts"), refetchInterval: 20_000 });
  const refresh = () => qc.invalidateQueries({ queryKey: ["alerts"] });
  const toggle = useMutation({ mutationFn: (a: PriceAlert) => v2.patch(`/alerts/${a.id}`, { active: !a.active }), onSuccess: refresh, onError: (e) => toast.error(e) });
  const remove = useMutation({ mutationFn: (id: number) => v2.del(`/alerts/${id}`), onSuccess: refresh, onError: (e) => toast.error(e) });
  const describe = (a: PriceAlert) =>
    a.condition === "above" ? t("alerts.d_above", "rises above {p}", { p: fmtPrice(a.target) })
      : a.condition === "below" ? t("alerts.d_below", "falls below {p}", { p: fmtPrice(a.target) })
        : t("alerts.d_move", "moves {p}% from {r}", { p: a.target, r: fmtPrice(a.reference_price) });

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<BellRing className="size-5" />}
        title={t("nav.alerts", "Price alerts")}
        subtitle={t("alerts.subtitle", "Get notified the moment a market reaches your level.")}
        actions={<Button icon={<Plus className="size-4" />} onClick={() => setModal({ open: true, alert: null })}>{t("alerts.new", "New price alert")}</Button>}
      />
      <Notice>
        {t("alerts.where", "Alerts appear in the app instantly and can also be forwarded to Discord, Slack or Telegram.")}{" "}
        <Link to="/settings?tab=notifications" className="text-primary hover:underline">{t("alerts.configure", "Configure channels")}</Link>
      </Notice>
      <Card>
        {list.isLoading ? <Skeleton className="m-4 h-40" /> : !list.data?.length ? (
          <EmptyState icon={<BellRing className="size-6" />} title={t("alerts.empty", "No alerts yet")} action={<Button size="sm" onClick={() => setModal({ open: true, alert: null })}>{t("alerts.new", "New price alert")}</Button>} />
        ) : (
          <Table>
            <thead>
              <tr>
                <Th>{t("market.pair", "Pair")}</Th><Th>{t("alerts.condition", "Condition")}</Th><Th align="end">{t("alerts.last", "Last price")}</Th>
                <Th>{t("alerts.note", "Note (optional)")}</Th><Th>{t("alerts.fired", "Triggered")}</Th><Th align="center">{t("alerts.active", "Active")}</Th><Th align="end" />
              </tr>
            </thead>
            <tbody>
              {list.data.map((a) => (
                <tr key={a.id} className={a.active ? undefined : "opacity-60"}>
                  <Td><Link to={`/markets/${symbolToSlug(a.symbol)}`} className="font-medium text-fg hover:text-primary">{a.symbol}</Link></Td>
                  <Td className="text-fg">{describe(a)} {a.repeat && <Badge tone="info"><Repeat className="size-3" />{t("alerts.repeats", "repeats")}</Badge>}</Td>
                  <Td align="end" className="num">{fmtPrice(a.last_price)}</Td>
                  <Td className="max-w-56 truncate text-muted">{a.note ?? "—"}</Td>
                  <Td className="text-muted">{a.trigger_count ? `${a.trigger_count}× · ${timeAgo(a.triggered_at)}` : t("alerts.never", "Not yet")}</Td>
                  <Td align="center"><Switch checked={a.active} onChange={() => toggle.mutate(a)} /></Td>
                  <Td align="end">
                    <IconButton label={t("common.edit", "Edit")} onClick={() => setModal({ open: true, alert: a })}><Pencil className="size-4" /></IconButton>
                    <IconButton label={t("common.delete", "Delete")} onClick={() => remove.mutate(a.id)}><Trash2 className="size-4" /></IconButton>
                  </Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <AlertModal open={modal.open} alert={modal.alert} onClose={() => setModal({ open: false, alert: null })} symbol={modal.alert?.symbol ?? "BTC/USDT"} price={modal.alert?.last_price ?? undefined} />
    </div>
  );
}
