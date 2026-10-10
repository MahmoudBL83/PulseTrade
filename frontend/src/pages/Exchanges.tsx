import { useState, type FormEvent } from "react";
import { useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, KeyRound, Plug, RotateCcw, ShieldAlert, Wallet } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import { useMarketExchanges } from "../lib/hooks";
import type { PaperSummary } from "../lib/types";
import { fmtAmount, fmtPct, fmtUsd, trendClass } from "../lib/format";
import { cn, toNumber } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, ConfirmButton, Field, Input, Modal, Notice, PageHeader, Select, Stat, Switch } from "../components/ui";

function PaperCard() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const [resetOpen, setResetOpen] = useState(false);
  const [start, setStart] = useState("10000");
  const paper = useQuery({ queryKey: ["paper"], queryFn: () => v2.get<PaperSummary>("/paper"), refetchInterval: 20_000 });
  const after = async (msg: string) => {
    toast.success(msg);
    await refresh();
    qc.invalidateQueries();
  };
  const connect = useMutation({ mutationFn: () => v2.post<PaperSummary>("/paper/connect"), onSuccess: () => after(t("paper.connected", "Paper trading account ready")), onError: (e) => toast.error(e) });
  const reset = useMutation({
    mutationFn: () => v2.post<PaperSummary>("/paper/reset", { starting_balance: toNumber(start, 10000) }),
    onSuccess: () => {
      setResetOpen(false);
      after(t("paper.reset_done", "Paper account reset"));
    },
    onError: (e) => toast.error(e),
  });
  const acc = paper.data?.account;
  return (
    <Card className="overflow-hidden">
      <div className="flex flex-wrap items-center gap-4 bg-[linear-gradient(120deg,var(--primary-soft),transparent)] p-5">
        <div className="flex size-11 items-center justify-center rounded-xl bg-primary text-primary-fg"><Wallet className="size-5" /></div>
        <div className="min-w-0 flex-1">
          <h2 className="font-semibold text-fg">{t("exchanges.paper_long", "Paper trading")}</h2>
          <p className="text-sm text-muted">{t("paper.desc", "A simulated exchange with live prices. Every feature works — no API keys, no risk.")}</p>
        </div>
        {paper.data?.connected ? (
          <Button variant="secondary" icon={<RotateCcw className="size-4" />} onClick={() => setResetOpen(true)}>{t("paper.reset", "Reset balance")}</Button>
        ) : (
          <Button loading={connect.isPending} onClick={() => connect.mutate()}>{t("paper.start", "Start paper trading")}</Button>
        )}
      </div>
      {acc && (
        <CardBody className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <Stat label={t("paper.equity", "Equity")} value={fmtUsd(acc.equity)} />
          <Stat label={t("paper.pnl", "P&L")} value={fmtUsd(acc.pnl)} tone={trendClass(acc.pnl)} hint={fmtPct(acc.pnl_pct)} />
          <Stat label={t("paper.start_bal", "Starting balance")} value={fmtUsd(acc.starting_balance, 0)} />
          <Stat label={t("paper.open_orders", "Open orders")} value={acc.open_orders} hint={`${t("paper.fee", "Fee")} ${(acc.fee_rate * 100).toFixed(2)}%`} />
          <div className="col-span-2 flex flex-wrap gap-2 sm:col-span-4">
            {acc.assets.slice(0, 10).map((a) => (
              <span key={a.currency} className="num rounded-lg border border-line px-2.5 py-1 text-xs text-fg">{fmtAmount(a.total)} {a.currency}</span>
            ))}
          </div>
        </CardBody>
      )}
      <Modal
        open={resetOpen}
        onClose={() => setResetOpen(false)}
        title={t("paper.reset", "Reset balance")}
        size="sm"
        footer={<><Button variant="secondary" onClick={() => setResetOpen(false)}>{t("common.cancel", "Cancel")}</Button><Button loading={reset.isPending} onClick={() => reset.mutate()}>{t("paper.reset", "Reset balance")}</Button></>}
      >
        <p className="mb-3 text-sm text-muted">{t("paper.reset_b", "Open paper orders are cancelled and the wallet is refilled with USDT.")}</p>
        <Field label={t("paper.start_bal", "Starting balance")}><Input inputMode="decimal" value={start} onChange={(e) => setStart(e.target.value)} suffix="USDT" /></Field>
      </Modal>
    </Card>
  );
}

function ConnectForm() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { refresh } = useAuth();
  const list = useMarketExchanges();
  const [form, setForm] = useState({ exchange_name: "", api_key: "", api_secret: "", password: "", demo: false });
  const exchanges = (list.data ?? []).filter((e) => !e.paper);
  const connect = useMutation({
    mutationFn: () => v1.post<{ message: string; ok?: boolean; status?: string }>("/api/v1/connect/", form),
    onSuccess: async (r) => {
      if (r.ok || r.status === "success") {
        toast.success(r.message);
        setForm({ exchange_name: "", api_key: "", api_secret: "", password: "", demo: false });
        await refresh();
        qc.invalidateQueries();
      } else toast.error(r.message);
    },
    onError: (e) => toast.error(e),
  });
  const submit = (e: FormEvent) => {
    e.preventDefault();
    connect.mutate();
  };
  return (
    <Card>
      <CardHeader title={t("exchanges.connect", "Connect an exchange")} subtitle={t("exchanges.connect_sub", "Your keys are encrypted at rest and never shown again.")} />
      <CardBody>
        <form onSubmit={submit} className="space-y-4">
          <Field label={t("exchanges.exchange", "Exchange")}>
            <Select required value={form.exchange_name} onChange={(e) => setForm({ ...form, exchange_name: e.target.value })}>
              <option value="" disabled>{t("exchanges.choose", "Choose…")}</option>
              {exchanges.map((e) => <option key={e.id} value={e.id}>{e.id}</option>)}
            </Select>
          </Field>
          <Field label={t("exchanges.api_key", "API key")}><Input required autoComplete="off" value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value.trim() })} /></Field>
          <Field label={t("exchanges.api_secret", "API secret")}><Input required type="password" autoComplete="off" value={form.api_secret} onChange={(e) => setForm({ ...form, api_secret: e.target.value.trim() })} /></Field>
          <Field label={t("exchanges.passphrase", "Passphrase")} hint={t("exchanges.passphrase_hint", "Only for exchanges that use one (OKX, KuCoin, Bitget…).")}>
            <Input type="password" autoComplete="off" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </Field>
          <Switch checked={form.demo} onChange={(v) => setForm({ ...form, demo: v })} label={t("exchanges.testnet", "Use the exchange's testnet / sandbox")} />
          <Notice tone="warning">
            <span className="flex gap-2"><ShieldAlert className="mt-0.5 size-4 shrink-0 text-primary" />{t("exchanges.safety", "Create a key with trading permission only — never enable withdrawals — and restrict it to this server's IP when your exchange supports it.")}</span>
          </Notice>
          <Button type="submit" className="w-full" icon={<KeyRound className="size-4" />} loading={connect.isPending}>{t("exchanges.verify_connect", "Verify & connect")}</Button>
        </form>
      </CardBody>
    </Card>
  );
}

export default function Exchanges() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const { user, refresh } = useAuth();
  const [params] = useSearchParams();
  const act = async (fn: () => Promise<{ message: string }>) => {
    try {
      const r = await fn();
      toast.success(r.message);
      await refresh();
      qc.invalidateQueries();
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <div className="space-y-5">
      <PageHeader icon={<Plug className="size-5" />} title={t("nav.exchanges", "Exchanges")} subtitle={t("exchanges.subtitle", "Connect accounts via API keys. The active exchange is used by the trading pages.")} />
      {params.get("welcome") && <Notice tone="success">{t("exchanges.welcome", "Welcome to PulseTrade! Start with paper trading below, or connect a real exchange.")}</Notice>}
      <PaperCard />
      <div className="grid gap-5 lg:grid-cols-[1fr_420px]">
        <Card>
          <CardHeader title={t("exchanges.connected", "Connected exchanges")} />
          <CardBody className="space-y-3">
            {!user?.exchanges.length && <p className="text-sm text-muted">{t("exchanges.none_yet", "No exchanges connected yet.")}</p>}
            {user?.exchanges.map((e) => (
              <div key={e.id} className={cn("flex flex-wrap items-center gap-3 rounded-xl border p-4", e.isActive ? "border-primary/60 bg-primary-soft/30" : "border-line")}>
                <div className="flex size-10 items-center justify-center rounded-lg bg-surface-2 text-sm font-bold text-fg uppercase">{e.name.slice(0, 2)}</div>
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-2 font-medium text-fg capitalize">
                    {e.paper ? t("exchanges.paper_long", "Paper trading") : e.name}
                    {e.isActive && <Badge tone="primary"><CheckCircle2 className="size-3" />{t("exchanges.active", "Active")}</Badge>}
                    {e.demo && <Badge tone="info">testnet</Badge>}
                  </p>
                  <p className="text-xs text-muted">{e.paper ? t("paper.simulated", "Simulated balances") : `${t("exchanges.api_key", "API key")} ••••${e.has_password ? ` · ${t("exchanges.passphrase", "Passphrase")}` : ""}`}</p>
                </div>
                {!e.isActive && <Button size="sm" variant="secondary" onClick={() => act(() => v1.post("/api/v1/fav_exchange/", { exchange_name: e.name }))}>{t("exchanges.make_active", "Make active")}</Button>}
                <ConfirmButton
                  title={t("exchanges.disconnect_q", "Disconnect {x}?", { x: e.paper ? t("exchanges.paper_long", "Paper trading") : e.name })}
                  body={t("exchanges.disconnect_b", "Bots and smart trades on this exchange stop working until you reconnect it.")}
                  confirmLabel={t("exchanges.disconnect", "Disconnect")}
                  onConfirm={() => act(() => v1.post("/api/v1/disconnect/", { exchange_name: e.name }))}
                >
                  {t("exchanges.disconnect", "Disconnect")}
                </ConfirmButton>
              </div>
            ))}
          </CardBody>
        </Card>
        <ConnectForm />
      </div>
    </div>
  );
}
