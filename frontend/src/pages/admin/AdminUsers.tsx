import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeftRight, ChevronLeft, ChevronRight, MessageSquare, Search, ShieldCheck, Users } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { request, v1, v2 } from "../../lib/api";
import type { Plan, Transaction, User } from "../../lib/types";
import { fmtAmount, fmtDate, fmtDateTime, fmtPrice, fmtUsd, timeAgo } from "../../lib/format";
import { initials, useDebounced } from "../../lib/utils";
import { Avatar, Badge, Button, Card, EmptyState, Field, IconButton, Input, Modal, PageHeader, Segmented, Select, SkeletonRows, Switch, Table, Td, Textarea, Th } from "../../components/ui";

type AdminUser = Omit<User, "exchanges"> & { bots: number; exchanges: string[]; subType: Plan | null };

export function Pager({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  const t = useT();
  if (total <= limit) return null;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-line px-4 py-3 text-sm text-muted">
      <span className="num">{t("admin.range", "{a}–{b} of {n}", { a: offset + 1, b: Math.min(offset + limit, total), n: total })}</span>
      <div className="flex gap-1">
        <IconButton label={t("common.prev", "Previous")} disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}><ChevronLeft className="size-4 rtl:rotate-180" /></IconButton>
        <IconButton label={t("common.next", "Next")} disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}><ChevronRight className="size-4 rtl:rotate-180" /></IconButton>
      </div>
    </div>
  );
}

function NotifyModal({ user, onClose }: { user: AdminUser | null; onClose: () => void }) {
  const t = useT();
  const toast = useToast();
  const [message, setMessage] = useState("");
  const send = useMutation({
    mutationFn: () => v1.post("/api/admin/v1/send_custom_notification", { message, user_id: user!.id }),
    onSuccess: () => {
      toast.success(t("admin.sent", "Message sent"));
      setMessage("");
      onClose();
    },
    onError: (e) => toast.error(e),
  });
  return (
    <Modal
      open={!!user}
      onClose={onClose}
      title={t("admin.notify_user", "Message {email}", { email: user?.email ?? "" })}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={send.isPending} disabled={!message.trim()} onClick={() => send.mutate()}>{t("support.send", "Send")}</Button></>}
    >
      <Field label={t("admin.notify_label", "In-app notification")} hint={t("admin.notify_hint", "Also forwarded to the user's Discord/Slack/Telegram channels if enabled.")}>
        <Textarea rows={4} value={message} onChange={(e) => setMessage(e.target.value)} />
      </Field>
    </Modal>
  );
}

export function AdminUsers() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [offset, setOffset] = useState(0);
  const [notify, setNotify] = useState<AdminUser | null>(null);
  const dq = useDebounced(q, 300);
  const limit = 50;
  const list = useQuery({
    queryKey: ["admin", "users", dq, offset],
    queryFn: () => v2.raw<{ data: AdminUser[]; total: number }>("/admin/users", { q: dq, limit, offset }),
    placeholderData: (prev) => prev,
  });
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => v2.get<Plan[]>("/plans") });
  const update = useMutation({
    mutationFn: ({ id, patch }: { id: number; patch: Record<string, unknown> }) => v2.patch(`/admin/users/${id}`, patch),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["admin", "users"] });
      toast.success(t("admin.updated", "User updated"));
    },
    onError: (e) => toast.error(e),
  });
  const rows = list.data?.data ?? [];

  return (
    <div className="space-y-5">
      <PageHeader icon={<Users className="size-5" />} title={t("admin.users", "Users")} subtitle={list.data ? t("admin.total_n", "{n} total", { n: list.data.total }) : undefined} />
      <Input
        className="max-w-md"
        value={q}
        onChange={(e) => {
          setQ(e.target.value);
          setOffset(0);
        }}
        placeholder={t("admin.search_users", "Search by email or name…")}
        prefix={<Search className="size-4" />}
      />
      <Card>
        {list.isLoading ? <SkeletonRows rows={8} className="p-4" /> : !rows.length ? <EmptyState title={t("admin.no_users", "No users match")} /> : (
          <Table>
            <thead>
              <tr>
                <Th>{t("admin.user", "User")}</Th><Th>{t("settings.plan", "Plan")}</Th><Th align="center">{t("admin.verified", "Verified")}</Th>
                <Th align="center">{t("admin.ip_check", "IP check")}</Th><Th align="center">2FA</Th><Th align="end">{t("nav.bots", "Bots")}</Th>
                <Th>{t("nav.exchanges", "Exchanges")}</Th><Th>{t("admin.joined", "Joined")}</Th><Th>{t("admin.last_login", "Last login")}</Th><Th align="end" />
              </tr>
            </thead>
            <tbody>
              {rows.map((u) => (
                <tr key={u.id}>
                  <Td>
                    <div className="flex items-center gap-2.5">
                      <Avatar src={u.img} name={initials(u.firstName, u.lastName, u.email)} size={30} />
                      <div className="min-w-0">
                        <p className="truncate font-medium text-fg">{[u.firstName, u.lastName].filter(Boolean).join(" ") || "—"}{u.demo && <Badge tone="info" className="ms-1.5">demo</Badge>}</p>
                        <p className="truncate text-xs text-muted">{u.email} · #{u.id}</p>
                      </div>
                    </div>
                  </Td>
                  <Td>
                    <Select className="h-8 w-32 text-xs capitalize" value={u.subType?.id ?? ""} onChange={(e) => update.mutate({ id: u.id, patch: { sub_type_id: Number(e.target.value) } })}>
                      {!u.subType && <option value="">—</option>}
                      {plans.data?.map((p) => <option key={p.id} value={p.id}>{p.type}</option>)}
                    </Select>
                  </Td>
                  <Td align="center"><Switch checked={u.is_verified} onChange={(v) => update.mutate({ id: u.id, patch: { is_verified: v } })} /></Td>
                  <Td align="center"><Switch checked={u.ip_check} onChange={(v) => update.mutate({ id: u.id, patch: { ip_check: v } })} /></Td>
                  <Td align="center">{u.totp_enabled ? <ShieldCheck className="mx-auto size-4 text-up" /> : <span className="text-muted">—</span>}</Td>
                  <Td align="end" className="num">{u.bots}</Td>
                  <Td><div className="flex max-w-56 flex-wrap gap-1">{u.exchanges.length ? u.exchanges.map((e) => <Badge key={e} className="capitalize">{e}</Badge>) : <span className="text-muted">—</span>}</div></Td>
                  <Td className="text-muted">{fmtDate(u.created_at)}</Td>
                  <Td className="text-muted">{u.last_login_at ? timeAgo(u.last_login_at) : "—"}</Td>
                  <Td align="end"><IconButton label={t("admin.message", "Send message")} onClick={() => setNotify(u)}><MessageSquare className="size-4" /></IconButton></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pager offset={offset} limit={limit} total={list.data.total} onChange={setOffset} />}
      </Card>
      <NotifyModal user={notify} onClose={() => setNotify(null)} />
    </div>
  );
}

/* ------------------------------------------------------------------ transactions */

type AdminTx = Transaction & { user_email: string | null };

export function AdminTransactions() {
  const t = useT();
  const [type, setType] = useState<"" | "buy" | "sell">("");
  const [exchange, setExchange] = useState("");
  const [offset, setOffset] = useState(0);
  const limit = 100;
  const exchanges = useQuery({ queryKey: ["admin", "exchanges", false], queryFn: () => v2.get<{ exchange: string; isActive: boolean }[]>("/admin/exchanges") });
  const list = useQuery({
    queryKey: ["admin", "transactions", type, exchange, offset],
    queryFn: () => request<{ data: AdminTx[]; total: number }>("/api/v2/admin/transactions", { query: { type, exchange, limit, offset } }),
    placeholderData: (prev) => prev,
  });
  const rows = list.data?.data ?? [];
  return (
    <div className="space-y-5">
      <PageHeader icon={<ArrowLeftRight className="size-5" />} title={t("admin.transactions", "Transactions")} subtitle={list.data ? t("admin.total_n", "{n} total", { n: list.data.total }) : undefined} />
      <div className="flex flex-wrap items-center gap-3">
        <Segmented size="xs" value={type} onChange={(v) => { setType(v); setOffset(0); }} options={[{ value: "", label: t("common.all", "All") }, { value: "buy", label: t("order.buy", "Buy"), tone: "up" }, { value: "sell", label: t("order.sell", "Sell"), tone: "down" }]} />
        <Select className="h-8 w-44 text-sm capitalize" value={exchange} onChange={(e) => { setExchange(e.target.value); setOffset(0); }}>
          <option value="">{t("admin.all_exchanges", "All exchanges")}</option>
          {exchanges.data?.map((e) => <option key={e.exchange} value={e.exchange}>{e.exchange}</option>)}
          <option value="paper">paper</option>
        </Select>
      </div>
      <Card>
        {list.isLoading ? <SkeletonRows rows={10} className="p-4" /> : !rows.length ? <EmptyState title={t("history.empty", "No transactions yet")} /> : (
          <Table>
            <thead>
              <tr>
                <Th>{t("history.date", "Date")}</Th><Th>{t("admin.user", "User")}</Th><Th>{t("nav.exchanges", "Exchange")}</Th><Th>{t("market.pair", "Pair")}</Th>
                <Th>{t("order.side", "Side")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th align="end">{t("order.price", "Price")}</Th>
                <Th align="end">{t("history.value", "Value")}</Th><Th>{t("history.source", "Source")}</Th><Th>{t("settings.status", "Status")}</Th>
              </tr>
            </thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.id}>
                  <Td className="text-muted">{fmtDateTime(x.timestamp ?? x.created_at)}</Td>
                  <Td className="max-w-52 truncate">{x.user_email ?? "—"}</Td>
                  <Td className="capitalize">{x.exchange}</Td>
                  <Td className="font-medium text-fg">{x.symbol}</Td>
                  <Td><Badge tone={x.type === "buy" ? "up" : "down"}>{x.type}</Badge></Td>
                  <Td align="end" className="num">{fmtAmount(x.amount)}</Td>
                  <Td align="end" className="num">{fmtPrice(x.price)}</Td>
                  <Td align="end" className="num">{fmtUsd(x.value)}</Td>
                  <Td className="text-muted">{x.bot_id ? `bot #${x.bot_id}` : x.sma_id ? `smart #${x.sma_id}` : t("history.manual", "Manual")}</Td>
                  <Td>{x.status ? <Badge tone="up">{t("history.ok", "OK")}</Badge> : <span title={typeof x.err_msg === "string" ? x.err_msg : JSON.stringify(x.err_msg)}><Badge tone="down">{t("history.failed", "Failed")}</Badge></span>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
        {list.data && <Pager offset={offset} limit={limit} total={list.data.total} onChange={setOffset} />}
      </Card>
    </div>
  );
}
