import { useEffect, useMemo, useState, type ChangeEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CreditCard, Download, ListChecks, Pencil, Plug, Plus, Search } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { v1, v2 } from "../../lib/api";
import type { Plan } from "../../lib/types";
import { fmtUsd } from "../../lib/format";
import { useDebounced } from "../../lib/utils";
import { Badge, Button, Card, EmptyState, Field, IconButton, Input, Modal, Notice, PageHeader, SkeletonRows, Switch, Table, Td, Th } from "../../components/ui";

/* ------------------------------------------------------------------ exchanges */

interface AdminExchange { exchange: string; isActive: boolean; listed: boolean; supported: boolean }

export function AdminExchanges() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [all, setAll] = useState(false);
  const [q, setQ] = useState("");
  const list = useQuery({ queryKey: ["admin", "exchanges", all], queryFn: () => v2.get<AdminExchange[]>("/admin/exchanges", { all: all ? 1 : undefined }), staleTime: 60_000 });
  const toggle = useMutation({
    mutationFn: ({ exchange, status }: { exchange: string; status: boolean }) => v1.post<{ message: string }>("/toggle_exchange", { exchange, status }),
    onSuccess: (r) => {
      toast.success(r.message);
      qc.invalidateQueries({ queryKey: ["admin", "exchanges"] });
      qc.invalidateQueries({ queryKey: ["market-exchanges"] });
    },
    onError: (e) => toast.error(e),
  });
  const rows = (list.data ?? []).filter((x) => x.exchange.includes(q.trim().toLowerCase()));
  const active = (list.data ?? []).filter((x) => x.isActive).length;
  return (
    <div className="space-y-5">
      <PageHeader icon={<Plug className="size-5" />} title={t("admin.exchanges", "Exchanges")} subtitle={t("admin.exchanges_sub", "{n} enabled for users. Only exchanges with full spot-trading support in ccxt can be enabled.", { n: active })} />
      <div className="flex flex-wrap items-center gap-4">
        <Input className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("admin.filter", "Filter…")} prefix={<Search className="size-4" />} />
        <Switch checked={all} onChange={setAll} label={t("admin.all_ccxt", "Show every ccxt exchange")} />
      </div>
      {all && list.isLoading && <Notice>{t("admin.loading_caps", "Checking capabilities of every exchange — this takes a few seconds the first time.")}</Notice>}
      <Card>
        {list.isLoading ? <SkeletonRows rows={8} className="p-4" /> : !rows.length ? <EmptyState title={t("admin.none", "Nothing found")} /> : (
          <Table>
            <thead><tr><Th>{t("admin.exchange", "Exchange")}</Th><Th>{t("admin.support_level", "Spot trading")}</Th><Th>{t("admin.listed", "Listed")}</Th><Th align="end">{t("admin.enabled", "Enabled")}</Th></tr></thead>
            <tbody>
              {rows.map((x) => (
                <tr key={x.exchange}>
                  <Td className="font-medium text-fg capitalize">{x.exchange}</Td>
                  <Td>{x.supported ? <Badge tone="up">{t("admin.supported", "Supported")}</Badge> : <Badge>{t("admin.partial", "Partial")}</Badge>}</Td>
                  <Td>{x.listed ? t("admin.yes", "Yes") : <span className="text-muted">{t("admin.no", "No")}</span>}</Td>
                  <Td align="end"><Switch checked={x.isActive} disabled={!x.supported && !x.isActive} onChange={(v) => toggle.mutate({ exchange: x.exchange, status: v })} /></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ indicator pairs */

interface AdminPair { id: number; pair: string; isActive: boolean }

export function AdminPairs() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [add, setAdd] = useState("");
  const [onlyActive, setOnlyActive] = useState(false);
  const dq = useDebounced(q, 300);
  const list = useQuery({ queryKey: ["admin", "pairs", dq], queryFn: () => v2.get<AdminPair[]>("/admin/pairs", { q: dq }), placeholderData: (prev) => prev });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "pairs"] });
  const toggle = useMutation({
    mutationFn: ({ pair, status }: { pair: string; status: boolean }) => v1.post<{ message: string }>("/toggle_pair", { pair, status }),
    onSuccess: refresh,
    onError: (e) => toast.error(e),
  });
  const importer = useMutation({
    mutationFn: () => v2.post<{ added: number }>("/admin/pairs/import", { quote: "USDT" }),
    onSuccess: (r) => {
      toast.success(t("admin.imported", "{n} pairs added (disabled until you enable them)", { n: r.added }));
      refresh();
    },
    onError: (e) => toast.error(e),
  });
  const rows = (list.data ?? []).filter((p) => !onlyActive || p.isActive);
  const enabled = (list.data ?? []).filter((p) => p.isActive).length;
  const addPair = () => {
    const pair = add.trim().toUpperCase();
    if (!/^[A-Z0-9]+\/[A-Z0-9]+$/.test(pair)) {
      toast.error(t("admin.pair_format", "Use the BASE/QUOTE format, e.g. SOL/USDT"));
      return;
    }
    toggle.mutate({ pair, status: true }, { onSuccess: () => setAdd("") });
  };
  return (
    <div className="space-y-5">
      <PageHeader
        icon={<ListChecks className="size-5" />}
        title={t("admin.pairs", "Indicator pairs")}
        subtitle={t("admin.pairs_sub", "Pairs scanned by the classic indicator streams and signals ({n} enabled).", { n: enabled })}
        actions={<Button variant="secondary" size="sm" icon={<Download className="size-4" />} loading={importer.isPending} onClick={() => importer.mutate()}>{t("admin.import", "Import USDT pairs")}</Button>}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Input className="max-w-xs" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("admin.filter", "Filter…")} prefix={<Search className="size-4" />} />
        <Switch checked={onlyActive} onChange={setOnlyActive} label={t("admin.only_enabled", "Only enabled")} />
        <div className="ms-auto flex items-center gap-2">
          <Input className="w-40" value={add} onChange={(e) => setAdd(e.target.value)} placeholder="SOL/USDT" onKeyDown={(e) => e.key === "Enter" && addPair()} />
          <Button size="sm" icon={<Plus className="size-4" />} onClick={addPair}>{t("common.add", "Add")}</Button>
        </div>
      </div>
      <Card>
        {list.isLoading ? <SkeletonRows rows={8} className="p-4" /> : !rows.length ? <EmptyState title={t("admin.none", "Nothing found")} /> : (
          <div className="grid gap-px bg-line sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {rows.slice(0, 600).map((p) => (
              <div key={p.id} className="flex items-center justify-between bg-surface px-4 py-2.5">
                <span className="text-sm font-medium text-fg">{p.pair}</span>
                <Switch checked={p.isActive} onChange={(v) => toggle.mutate({ pair: p.pair, status: v })} />
              </div>
            ))}
          </div>
        )}
        {rows.length > 600 && <p className="border-t border-line px-4 py-3 text-xs text-muted">{t("admin.more_pairs", "Showing 600 of {n} — refine the filter.", { n: rows.length })}</p>}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ plans */

const UNLIMITED = 1e8;

function PlanModal({ plan, onClose }: { plan: Plan | null; onClose: () => void }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [f, setF] = useState({ name_en: "", name_ar: "", price: "", max_bots: "", max_sma: "", trial_days: "", stripe_id: "" });
  useEffect(() => {
    if (plan) {
      setF({
        name_en: plan.type, name_ar: plan.type_ar ?? "", price: String(plan.price ?? 0),
        max_bots: plan.max_bots >= UNLIMITED ? "" : String(plan.max_bots), max_sma: plan.max_sma >= UNLIMITED ? "" : String(plan.max_sma),
        trial_days: String(plan.trial_days ?? 0), stripe_id: plan.stripe_id ?? "",
      });
    }
  }, [plan]);
  const save = useMutation({
    mutationFn: () => v1.post("/admin/pricing", { id: plan!.id, ...f, stripe_id: f.stripe_id || null }),
    onSuccess: () => {
      toast.success(t("admin.plan_saved", "Plan saved"));
      qc.invalidateQueries({ queryKey: ["plans"] });
      onClose();
    },
    onError: (e) => toast.error(e),
  });
  const set = (k: keyof typeof f) => (e: ChangeEvent<HTMLInputElement>) => setF({ ...f, [k]: e.target.value });
  return (
    <Modal
      open={!!plan}
      onClose={onClose}
      title={t("admin.edit_plan", "Edit plan")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={save.isPending} disabled={!f.name_en.trim()} onClick={() => save.mutate()}>{t("common.save", "Save")}</Button></>}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label={t("admin.name_en", "Name (English)")}><Input value={f.name_en} onChange={set("name_en")} /></Field>
        <Field label={t("admin.name_ar", "Name (Arabic)")}><Input dir="rtl" value={f.name_ar} onChange={set("name_ar")} /></Field>
        <Field label={t("admin.price", "Monthly price")}><Input inputMode="decimal" value={f.price} onChange={set("price")} suffix="USD" /></Field>
        <Field label={t("admin.trial", "Trial days")}><Input inputMode="numeric" value={f.trial_days} onChange={set("trial_days")} /></Field>
        <Field label={t("admin.max_bots", "Max active bots")} hint={t("admin.empty_unl", "Empty = unlimited")}><Input inputMode="numeric" value={f.max_bots} onChange={set("max_bots")} /></Field>
        <Field label={t("admin.max_sma", "Max smart trades")} hint={t("admin.empty_unl", "Empty = unlimited")}><Input inputMode="numeric" value={f.max_sma} onChange={set("max_sma")} /></Field>
        <Field label={t("admin.stripe_id", "Stripe price id")} className="sm:col-span-2" hint={t("admin.stripe_hint", "price_… from the Stripe dashboard; required for paid checkout.")}><Input value={f.stripe_id} onChange={set("stripe_id")} placeholder="price_…" /></Field>
      </div>
    </Modal>
  );
}

export function AdminPlans() {
  const t = useT();
  const [edit, setEdit] = useState<Plan | null>(null);
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => v2.get<Plan[]>("/plans") });
  const lim = (n: number) => (n >= UNLIMITED ? "∞" : n);
  const sorted = useMemo(() => [...(plans.data ?? [])].sort((a, b) => (a.price ?? 0) - (b.price ?? 0)), [plans.data]);
  return (
    <div className="space-y-5">
      <PageHeader icon={<CreditCard className="size-5" />} title={t("admin.plans", "Plans")} subtitle={t("admin.plans_sub", "Limits apply immediately to every user on the plan.")} />
      <Card>
        {plans.isLoading ? <SkeletonRows rows={3} className="p-4" /> : (
          <Table>
            <thead><tr><Th>{t("settings.plan", "Plan")}</Th><Th align="end">{t("admin.price", "Monthly price")}</Th><Th align="end">{t("admin.max_bots", "Max active bots")}</Th><Th align="end">{t("admin.max_sma", "Max smart trades")}</Th><Th align="end">{t("admin.trial", "Trial days")}</Th><Th>Stripe</Th><Th align="end" /></tr></thead>
            <tbody>
              {sorted.map((p) => (
                <tr key={p.id}>
                  <Td><span className="font-medium text-fg capitalize">{p.type}</span>{p.type_ar && <span className="ms-2 text-muted" dir="rtl">{p.type_ar}</span>}</Td>
                  <Td align="end" className="num">{p.price ? fmtUsd(p.price) : t("pricing.free", "Free")}</Td>
                  <Td align="end" className="num">{lim(p.max_bots)}</Td>
                  <Td align="end" className="num">{lim(p.max_sma)}</Td>
                  <Td align="end" className="num">{p.trial_days ?? 0}</Td>
                  <Td>{p.stripe_id ? <Badge tone="up">{p.stripe_id.slice(0, 14)}…</Badge> : p.price ? <Badge tone="down">{t("admin.missing", "missing")}</Badge> : <span className="text-muted">—</span>}</Td>
                  <Td align="end"><IconButton label={t("common.edit", "Edit")} onClick={() => setEdit(p)}><Pencil className="size-4" /></IconButton></Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
      <PlanModal plan={edit} onClose={() => setEdit(null)} />
    </div>
  );
}
