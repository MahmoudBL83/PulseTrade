import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { ArrowDownToLine, ArrowLeftRight, ArrowUpFromLine, Copy, RefreshCcw, Wallet as WalletIcon } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import { fmtAmount, fmtDateTime, fmtPrice } from "../lib/format";
import { toNumber } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, EmptyState, Field, Input, Modal, Notice, PageHeader, Segmented, Select, Skeleton, Table, Tabs, Td, Th } from "../components/ui";
import { useFreeBalances } from "../components/orders";

interface Currency {
  code: string;
  name?: string;
  networks?: Record<string, { id?: string; network?: string; deposit?: boolean; withdraw?: boolean; fee?: number | null; limits?: { withdraw?: { min?: number | null } } }>;
}

interface Movement {
  id?: string;
  txid?: string;
  timestamp?: number;
  currency?: string;
  amount?: number;
  network?: string;
  address?: string;
  status?: string;
}

type Caps = Record<string, boolean>;

function useCurrencies(exchange?: string) {
  return useQuery({
    queryKey: ["currencies", exchange],
    queryFn: () => v1.get<Currency[]>(`/api/v1/currencies/${encodeURIComponent(exchange!)}`),
    enabled: !!exchange,
    staleTime: 10 * 60_000,
  });
}

function networksOf(c?: Currency, kind: "deposit" | "withdraw" = "deposit") {
  return Object.entries(c?.networks ?? {})
    .filter(([, n]) => n?.[kind] !== false)
    .map(([key, n]) => ({ key, label: n.network || n.id || key, fee: n.fee, min: n.limits?.withdraw?.min }));
}

function MovementTable({ rows, empty }: { rows?: Movement[]; empty: string }) {
  const t = useT();
  if (!rows) return <Skeleton className="m-4 h-24" />;
  if (!rows.length) return <EmptyState title={empty} />;
  return (
    <Table>
      <thead><tr><Th>{t("market.time", "Time")}</Th><Th>{t("wallet.coin", "Coin")}</Th><Th align="end">{t("order.amount", "Amount")}</Th><Th>{t("wallet.network", "Network")}</Th><Th>{t("order.status", "Status")}</Th><Th>TxID</Th></tr></thead>
      <tbody>
        {rows.slice(0, 50).map((m, i) => (
          <tr key={m.id ?? i}>
            <Td className="text-muted">{fmtDateTime(m.timestamp)}</Td>
            <Td className="font-medium">{m.currency}</Td>
            <Td align="end" className="num">{fmtAmount(m.amount)}</Td>
            <Td className="text-muted">{m.network ?? "—"}</Td>
            <Td><Badge tone={m.status === "ok" ? "up" : m.status === "failed" ? "down" : "neutral"}>{m.status ?? "—"}</Badge></Td>
            <Td className="max-w-40 truncate font-mono text-xs text-muted">{m.txid ?? "—"}</Td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
}

function Deposit({ exchange, caps }: { exchange: string; caps: Caps }) {
  const t = useT();
  const toast = useToast();
  const currencies = useCurrencies(exchange);
  const [code, setCode] = useState("USDT");
  const cur = currencies.data?.find((c) => c.code === code);
  const nets = networksOf(cur, "deposit");
  const [net, setNet] = useState("");
  const [qr, setQr] = useState<string | null>(null);
  useEffect(() => setNet(nets[0]?.key ?? ""), [code, currencies.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const address = useMutation({
    mutationFn: () => v1.post<{ address: string; tag?: string | null; network?: string; message: string }>("/api/v1/deposit/", { symbol: code, network: net || undefined }),
    onSuccess: async (r) => setQr(await QRCode.toDataURL(r.address, { margin: 1, width: 220 })),
    onError: (e) => toast.error(e),
  });
  const history = useQuery({ queryKey: ["deposits", exchange], queryFn: () => v1.get<Movement[]>("/api/v1/deposits/"), enabled: caps.fetchDeposits });
  if (!caps.fetchDepositAddress) return <Notice>{t("wallet.no_deposit", "Deposits are not available on this exchange through the API.")}</Notice>;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("wallet.deposit", "Deposit")} />
        <CardBody className="space-y-4">
          <Field label={t("wallet.coin", "Coin")}>
            {currencies.isLoading ? <Skeleton className="h-10" /> : (
              <Select value={code} onChange={(e) => { setCode(e.target.value); address.reset(); setQr(null); }}>
                {(currencies.data ?? []).map((c) => <option key={c.code} value={c.code}>{c.code}{c.name && c.name !== c.code ? ` — ${c.name}` : ""}</option>)}
              </Select>
            )}
          </Field>
          {!!nets.length && (
            <Field label={t("wallet.network", "Network")}>
              <Select value={net} onChange={(e) => { setNet(e.target.value); address.reset(); setQr(null); }}>
                {nets.map((n) => <option key={n.key} value={n.key}>{n.label}</option>)}
              </Select>
            </Field>
          )}
          <Button className="w-full" loading={address.isPending} onClick={() => address.mutate()}>{t("wallet.get_address", "Show deposit address")}</Button>
          {address.data && (
            <div className="flex flex-col items-center gap-3 rounded-xl border border-line p-4">
              {qr && <img src={qr} alt="" width={220} height={220} className="rounded-lg bg-white p-2" />}
              <p className="w-full break-all rounded-lg bg-surface-2 p-3 text-center font-mono text-sm text-fg">{address.data.address}</p>
              {address.data.tag && <p className="text-sm text-fg">{t("wallet.tag", "Memo / tag")}: <span className="font-mono">{address.data.tag}</span></p>}
              <Button size="sm" variant="secondary" icon={<Copy className="size-4" />} onClick={() => navigator.clipboard?.writeText(address.data!.address).then(() => toast.success(t("common.copied", "Copied")))}>{t("common.copy", "Copy")}</Button>
              <Notice tone="warning">{t("wallet.only_send", "Send only {c} on the {n} network to this address.", { c: code, n: net || "—" })}</Notice>
            </div>
          )}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("wallet.deposit_history", "Recent deposits")} />
        {caps.fetchDeposits ? <MovementTable rows={history.data} empty={t("wallet.no_deposits", "No deposits yet")} /> : <EmptyState title={t("wallet.no_history_api", "History is not available for this exchange")} />}
      </Card>
    </div>
  );
}

function Withdraw({ exchange, caps }: { exchange: string; caps: Caps }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const currencies = useCurrencies(exchange);
  const balances = useFreeBalances(exchange);
  const [form, setForm] = useState({ currency: "USDT", network: "", address: "", tag: "", amount: "" });
  const [confirm, setConfirm] = useState(false);
  const cur = currencies.data?.find((c) => c.code === form.currency);
  const nets = networksOf(cur, "withdraw");
  const netInfo = nets.find((n) => n.key === form.network);
  useEffect(() => setForm((f) => ({ ...f, network: nets[0]?.key ?? "" })), [form.currency, currencies.data]); // eslint-disable-line react-hooks/exhaustive-deps
  const history = useQuery({ queryKey: ["withdrawals", exchange], queryFn: () => v1.get<Movement[]>("/api/v1/withdrawals/"), enabled: caps.fetchWithdrawals });
  const send = useMutation({
    mutationFn: () => v1.post<{ message: string }>("/api/v1/withdraw/", { currency: form.currency, network: form.network || undefined, recipient_address: form.address, tag: form.tag || undefined, amount: toNumber(form.amount) }),
    onSuccess: (r) => {
      toast.success(r.message);
      setConfirm(false);
      setForm((f) => ({ ...f, address: "", tag: "", amount: "" }));
      qc.invalidateQueries({ queryKey: ["withdrawals"] });
      qc.invalidateQueries({ queryKey: ["free-balance"] });
    },
    onError: (e) => toast.error(e),
  });
  if (!caps.withdraw) return <Notice>{t("wallet.no_withdraw", "Withdrawals are not available on this exchange through the API.")}</Notice>;
  const free = balances.data?.[form.currency] ?? 0;
  const invalid = !form.address.trim() || !(toNumber(form.amount) > 0) || toNumber(form.amount) > free;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("wallet.withdraw", "Withdraw")} />
        <CardBody className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("wallet.coin", "Coin")}>
              <Select value={form.currency} onChange={(e) => setForm({ ...form, currency: e.target.value })}>
                {(currencies.data ?? []).map((c) => <option key={c.code} value={c.code}>{c.code}</option>)}
              </Select>
            </Field>
            <Field label={t("wallet.network", "Network")}>
              <Select value={form.network} onChange={(e) => setForm({ ...form, network: e.target.value })}>
                {nets.length ? nets.map((n) => <option key={n.key} value={n.key}>{n.label}</option>) : <option value="">—</option>}
              </Select>
            </Field>
          </div>
          <Field label={t("wallet.address", "Recipient address")}><Input className="font-mono" value={form.address} onChange={(e) => setForm({ ...form, address: e.target.value })} /></Field>
          <Field label={t("wallet.tag_opt", "Memo / tag (if required)")}><Input value={form.tag} onChange={(e) => setForm({ ...form, tag: e.target.value })} /></Field>
          <Field label={t("order.amount", "Amount")} hint={`${t("order.available", "Available")}: ${fmtAmount(free)} ${form.currency}${netInfo?.fee ? ` · ${t("wallet.fee", "Network fee")} ${netInfo.fee}` : ""}${netInfo?.min ? ` · min ${netInfo.min}` : ""}`}>
            <Input inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value })} suffix={<button type="button" className="text-primary" onClick={() => setForm({ ...form, amount: String(free) })}>MAX</button>} />
          </Field>
          <Button className="w-full" variant="danger" disabled={invalid} onClick={() => setConfirm(true)}>{t("wallet.review", "Review withdrawal")}</Button>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("wallet.withdraw_history", "Recent withdrawals")} />
        {caps.fetchWithdrawals ? <MovementTable rows={history.data} empty={t("wallet.no_withdrawals", "No withdrawals yet")} /> : <EmptyState title={t("wallet.no_history_api", "History is not available for this exchange")} />}
      </Card>
      <Modal
        open={confirm}
        onClose={() => setConfirm(false)}
        title={t("wallet.confirm", "Confirm withdrawal")}
        size="sm"
        footer={<><Button variant="secondary" onClick={() => setConfirm(false)}>{t("common.cancel", "Cancel")}</Button><Button variant="danger" loading={send.isPending} onClick={() => send.mutate()}>{t("wallet.send", "Send")}</Button></>}
      >
        <div className="space-y-2 text-sm">
          <p className="num text-lg font-semibold text-fg">{form.amount} {form.currency}</p>
          <p className="text-muted">{t("wallet.network", "Network")}: {form.network || "—"}</p>
          <p className="break-all font-mono text-fg">{form.address}</p>
          {form.tag && <p className="text-muted">{t("wallet.tag", "Memo / tag")}: {form.tag}</p>}
          <Notice tone="warning">{t("wallet.irreversible", "Blockchain transfers cannot be reversed. Double-check the address and network.")}</Notice>
        </div>
      </Modal>
    </div>
  );
}

function Transfer({ exchange, caps }: { exchange: string; caps: Caps }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [side, setSide] = useState<"funding" | "spot">("funding");
  const [coin, setCoin] = useState("USDT");
  const [amount, setAmount] = useState("");
  const history = useQuery({ queryKey: ["transfers", exchange], queryFn: () => v2.get<Movement[]>("/wallet/transfers"), enabled: caps.fetchTransfers });
  const go = useMutation({
    mutationFn: () => v1.post<{ message: string }>("/api/v1/transfer/", { side, symbol: coin, amount: toNumber(amount) }),
    onSuccess: (r) => {
      toast.success(r.message);
      setAmount("");
      qc.invalidateQueries({ queryKey: ["transfers"] });
      qc.invalidateQueries({ queryKey: ["free-balance"] });
    },
    onError: (e) => toast.error(e),
  });
  if (!caps.transfer) return <Notice>{t("wallet.no_transfer", "This exchange has a single wallet — internal transfers are not needed.")}</Notice>;
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card>
        <CardHeader title={t("wallet.transfer", "Transfer between wallets")} />
        <CardBody className="space-y-4">
          <Segmented value={side} onChange={setSide} className="w-full" options={[{ value: "funding", label: t("wallet.to_funding", "Spot → Funding") }, { value: "spot", label: t("wallet.to_spot", "Funding → Spot") }]} />
          <div className="grid grid-cols-2 gap-3">
            <Field label={t("wallet.coin", "Coin")}><Input value={coin} onChange={(e) => setCoin(e.target.value.toUpperCase())} /></Field>
            <Field label={t("order.amount", "Amount")}><Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} /></Field>
          </div>
          <Button className="w-full" icon={<ArrowLeftRight className="size-4" />} loading={go.isPending} disabled={!(toNumber(amount) > 0) || !coin} onClick={() => go.mutate()}>{t("wallet.transfer_btn", "Transfer")}</Button>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("wallet.transfer_history", "Recent transfers")} />
        {caps.fetchTransfers ? <MovementTable rows={history.data} empty={t("wallet.no_transfers", "No transfers yet")} /> : <EmptyState title={t("wallet.no_history_api", "History is not available for this exchange")} />}
      </Card>
    </div>
  );
}

function Convert({ exchange }: { exchange: string }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const balances = useFreeBalances(exchange);
  const markets = useQuery({ queryKey: ["all-markets", exchange], queryFn: () => v1.get<string[]>(`/api/v1/all_markets/${encodeURIComponent(exchange)}`), staleTime: 10 * 60_000 });
  const [from, setFrom] = useState("USDT");
  const [to, setTo] = useState("BTC");
  const [amount, setAmount] = useState("");
  const assets = useMemo(() => [...new Set((markets.data ?? []).flatMap((s) => s.split("/")))].sort(), [markets.data]);
  // direct pair FROM/TO -> sell FROM; inverse TO/FROM -> buy TO with FROM
  const direct = markets.data?.includes(`${from}/${to}`);
  const inverse = markets.data?.includes(`${to}/${from}`);
  const symbol = direct ? `${from}/${to}` : inverse ? `${to}/${from}` : null;
  const quote = useQuery({ queryKey: ["ticker-convert", exchange, symbol], queryFn: () => v2.get<{ last: number }>("/market/ticker", { exchange, symbol: symbol! }), enabled: !!symbol, refetchInterval: 10_000 });
  const px = quote.data?.last ?? 0;
  const amt = toNumber(amount);
  const receive = direct ? amt * px : inverse && px ? amt / px : 0;
  const go = useMutation({
    mutationFn: () =>
      v1.post<{ message: string }>("/api/v1/convert/", direct
        ? { source_asset: from, target_asset: to, side: "1", amount: amt, order_type: "market" }
        : { source_asset: to, target_asset: from, side: "0", amount: receive * 0.998, order_type: "market" }),
    onSuccess: (r) => {
      toast.success(r.message);
      setAmount("");
      qc.invalidateQueries({ queryKey: ["free-balance"] });
      qc.invalidateQueries({ queryKey: ["portfolio"] });
    },
    onError: (e) => toast.error(e),
  });
  const free = balances.data?.[from] ?? 0;
  return (
    <Card className="mx-auto max-w-lg">
      <CardHeader title={t("wallet.convert", "Convert")} subtitle={t("wallet.convert_sub", "Market conversion through the exchange's order book.")} />
      <CardBody className="space-y-4">
        <Field label={t("wallet.from", "From")} hint={`${t("order.available", "Available")}: ${fmtAmount(free)} ${from}`}>
          <div className="flex gap-2">
            <Select value={from} onChange={(e) => setFrom(e.target.value)} className="w-32">{assets.map((a) => <option key={a}>{a}</option>)}</Select>
            <Input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} suffix={<button type="button" className="text-primary" onClick={() => setAmount(String(free))}>MAX</button>} />
          </div>
        </Field>
        <div className="flex justify-center">
          <button type="button" onClick={() => { setFrom(to); setTo(from); }} className="rounded-full border border-line p-2 text-muted hover:text-fg" aria-label={t("wallet.swap", "Swap")}><RefreshCcw className="size-4" /></button>
        </div>
        <Field label={t("wallet.to", "To")}>
          <div className="flex gap-2">
            <Select value={to} onChange={(e) => setTo(e.target.value)} className="w-32">{assets.map((a) => <option key={a}>{a}</option>)}</Select>
            <Input readOnly value={receive ? `≈ ${fmtAmount(receive)}` : ""} />
          </div>
        </Field>
        {symbol ? <p className="num text-xs text-muted">{symbol} · {fmtPrice(px)}</p> : <Notice tone="warning">{t("wallet.no_pair", "No direct market between {a} and {b} on this exchange.", { a: from, b: to })}</Notice>}
        <Button className="w-full" loading={go.isPending} disabled={!symbol || !(amt > 0) || amt > free} onClick={() => go.mutate()}>{t("wallet.convert_btn", "Convert")}</Button>
      </CardBody>
    </Card>
  );
}

export default function Wallet() {
  const t = useT();
  const { user } = useAuth();
  const active = user?.exchanges.find((e) => e.isActive);
  const [tab, setTab] = useState<"deposit" | "withdraw" | "transfer" | "convert">("deposit");
  const caps = useQuery({ queryKey: ["wallet-caps", active?.name], queryFn: () => v2.get<Caps>("/wallet/capabilities"), enabled: !!active });
  if (!active) {
    return (
      <>
        <PageHeader icon={<WalletIcon className="size-5" />} title={t("nav.wallet", "Wallet")} />
        <Card><EmptyState title={t("dash.onboard_title", "Connect an exchange to get started")} action={<Link to="/exchanges"><Button>{t("dash.onboard_cta", "Connect now")}</Button></Link>} /></Card>
      </>
    );
  }
  return (
    <div className="space-y-5">
      <PageHeader icon={<WalletIcon className="size-5" />} title={t("nav.wallet", "Wallet")} subtitle={t("wallet.subtitle", "Move funds on {x}.", { x: active.paper ? t("exchanges.paper_long", "Paper trading") : active.name })} />
      {active.paper && <Notice>{t("wallet.paper", "Paper accounts can convert, but deposits, withdrawals and transfers are simulated by resetting the balance on the Exchanges page.")}</Notice>}
      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: "deposit", label: <span className="flex items-center gap-1.5"><ArrowDownToLine className="size-4" />{t("wallet.deposit", "Deposit")}</span> },
          { value: "withdraw", label: <span className="flex items-center gap-1.5"><ArrowUpFromLine className="size-4" />{t("wallet.withdraw", "Withdraw")}</span> },
          { value: "transfer", label: <span className="flex items-center gap-1.5"><ArrowLeftRight className="size-4" />{t("wallet.transfer_short", "Transfer")}</span> },
          { value: "convert", label: <span className="flex items-center gap-1.5"><RefreshCcw className="size-4" />{t("wallet.convert", "Convert")}</span> },
        ]}
      />
      {!caps.data ? <Skeleton className="h-64" /> : (
        <>
          {tab === "deposit" && <Deposit exchange={active.name} caps={caps.data} />}
          {tab === "withdraw" && <Withdraw exchange={active.name} caps={caps.data} />}
          {tab === "transfer" && <Transfer exchange={active.name} caps={caps.data} />}
          {tab === "convert" && <Convert exchange={active.name} />}
        </>
      )}
    </div>
  );
}
