import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Bell, CheckCheck, Settings2, Trash2 } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import type { Notification } from "../lib/types";
import { fmtDateTime } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Button, Card, EmptyState, IconButton, PageHeader, Segmented, Skeleton } from "../components/ui";

export default function Notifications() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const [filter, setFilter] = useState<"all" | "unread">("all");
  const [limit, setLimit] = useState(50);
  const list = useQuery({
    queryKey: ["notifications", "page", filter, limit],
    queryFn: () => v2.raw<{ data: Notification[]; unread: number }>("/notifications", { limit, unread: filter === "unread" ? 1 : undefined }),
  });
  const after = () => {
    qc.invalidateQueries({ queryKey: ["notifications"] });
    refresh();
  };
  const readAll = useMutation({ mutationFn: () => v2.post("/notifications/read"), onSuccess: after, onError: (e) => toast.error(e) });
  const readOne = useMutation({ mutationFn: (id: number) => v2.post("/notifications/read", { ids: [id] }), onSuccess: after });
  const del = useMutation({ mutationFn: (id: number) => v2.del(`/notifications/${id}`), onSuccess: after, onError: (e) => toast.error(e) });
  const rows = list.data?.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Bell className="size-5" />}
        title={t("nav.notifications", "Notifications")}
        subtitle={t("notifications.subtitle", "{n} unread", { n: list.data?.unread ?? 0 })}
        actions={
          <>
            <Segmented size="xs" value={filter} onChange={setFilter} options={[{ value: "all", label: t("common.all", "All") }, { value: "unread", label: t("notifications.unread", "Unread") }]} />
            <Button size="sm" variant="secondary" icon={<CheckCheck className="size-4" />} loading={readAll.isPending} onClick={() => readAll.mutate()}>{t("notifications.mark_all", "Mark all read")}</Button>
            <Link to="/settings?tab=notifications"><Button size="sm" variant="ghost" icon={<Settings2 className="size-4" />}>{t("notifications.channels", "Channels")}</Button></Link>
          </>
        }
      />
      <Card>
        {list.isLoading ? <Skeleton className="m-4 h-64" /> : !rows.length ? <EmptyState icon={<Bell className="size-6" />} title={t("notifications.empty", "You're all caught up")} /> : (
          <ul>
            {rows.map((n) => (
              <li key={n.id} className={cn("flex items-start gap-3 border-b border-line/60 px-5 py-3 last:border-0", !n.read && "bg-primary-soft/30")}>
                <span className={cn("mt-1.5 size-2 shrink-0 rounded-full", n.read ? "bg-transparent" : "bg-primary")} />
                <button type="button" className="min-w-0 flex-1 text-start" onClick={() => !n.read && readOne.mutate(n.id)}>
                  <p className="text-sm text-fg">{n.content}</p>
                  <p className="mt-1 flex flex-wrap items-center gap-2 text-xs text-muted">
                    {n.type && n.type !== "system" && <Badge>{n.type}</Badge>}
                    {n.type === "system" && <Badge tone="info">{t("notifications.system", "System")}</Badge>}
                    {n.exchange && <span className="capitalize">{n.exchange}</span>}
                    <span>{fmtDateTime(n.date)}</span>
                  </p>
                </button>
                <IconButton label={t("common.delete", "Delete")} onClick={() => del.mutate(n.id)}><Trash2 className="size-4" /></IconButton>
              </li>
            ))}
          </ul>
        )}
        {rows.length >= limit && (
          <div className="border-t border-line p-3 text-center">
            <Button variant="ghost" size="sm" onClick={() => setLimit(limit + 50)}>{t("common.load_more", "Load more")}</Button>
          </div>
        )}
      </Card>
    </div>
  );
}
