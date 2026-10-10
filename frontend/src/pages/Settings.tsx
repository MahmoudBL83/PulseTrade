import { useEffect, useState, type ReactNode } from "react";
import { Link, useSearchParams } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import QRCode from "qrcode";
import { BellRing, CreditCard, ExternalLink, KeyRound, Monitor, Moon, Palette, Send, Settings as SettingsIcon, ShieldCheck, Sun, User as UserIcon } from "lucide-react";
import { useAuth } from "../context/auth";
import { useTheme, type ThemeChoice } from "../context/theme";
import { useToast } from "../context/toast";
import { useI18n, useT, type Lang } from "../i18n";
import { request, v2 } from "../lib/api";
import type { LoginEvent, Plan, User } from "../lib/types";
import { fmtDate, fmtDateTime, fmtUsd } from "../lib/format";
import { cn, initials } from "../lib/utils";
import { Avatar, Badge, Button, Card, CardBody, CardHeader, Field, Input, Notice, PageHeader, Skeleton, Switch, Table, Tabs, Td, Th } from "../components/ui";

type Tab = "profile" | "preferences" | "security" | "notifications" | "billing";

/* ------------------------------------------------------------------ profile */

function ProfileTab({ user }: { user: User }) {
  const t = useT();
  const toast = useToast();
  const { setUser } = useAuth();
  const [f, setF] = useState({ firstName: user.firstName ?? "", lastName: user.lastName ?? "", img: user.img?.endsWith("/avatars/01.png") ? "" : user.img ?? "" });
  const save = useMutation({
    mutationFn: () => v2.patch<User>("/auth/me", f),
    onSuccess: (u) => {
      setUser(u);
      toast.success(t("settings.saved", "Settings saved"));
    },
    onError: (e) => toast.error(e),
  });
  return (
    <Card>
      <CardHeader title={t("settings.profile", "Profile")} subtitle={t("settings.profile_sub", "How you appear in PulseTrade.")} />
      <CardBody className="space-y-5">
        <div className="flex items-center gap-4">
          <Avatar src={f.img || null} name={initials(f.firstName, f.lastName, user.email)} size={64} />
          <div>
            <p className="font-medium text-fg">{[f.firstName, f.lastName].filter(Boolean).join(" ") || user.email}</p>
            <p className="text-sm text-muted">{user.email}</p>
            <p className="text-xs text-muted">{t("settings.member_since", "Member since {d}", { d: fmtDate(user.created_at) })}</p>
          </div>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("auth.first_name", "First name")}><Input value={f.firstName} maxLength={120} onChange={(e) => setF({ ...f, firstName: e.target.value })} /></Field>
          <Field label={t("auth.last_name", "Last name")}><Input value={f.lastName} maxLength={120} onChange={(e) => setF({ ...f, lastName: e.target.value })} /></Field>
          <Field label={t("auth.email", "Email")} hint={t("settings.email_fixed", "Contact support to change your email.")}><Input value={user.email} disabled /></Field>
          <Field label={t("settings.avatar", "Avatar URL")} hint={t("settings.avatar_hint", "An https:// image link. Leave empty for initials.")}><Input value={f.img} onChange={(e) => setF({ ...f, img: e.target.value })} placeholder="https://…" /></Field>
        </div>
        <div className="flex justify-end"><Button loading={save.isPending} onClick={() => save.mutate()}>{t("common.save", "Save")}</Button></div>
      </CardBody>
    </Card>
  );
}

/* ------------------------------------------------------------------ preferences */

function PreferencesTab({ user }: { user: User }) {
  const t = useT();
  const toast = useToast();
  const { setUser } = useAuth();
  const { theme, setTheme } = useTheme();
  const { lang, setLang } = useI18n();
  const persist = (prefs: Partial<{ theme: ThemeChoice; lang: Lang }>) =>
    v2.patch<User>("/auth/me", { preferences: prefs }).then(setUser).catch((e) => toast.error(e));
  const themes: { value: ThemeChoice; label: string; icon: typeof Sun }[] = [
    { value: "dark", label: t("settings.dark", "Dark"), icon: Moon },
    { value: "light", label: t("settings.light", "Light"), icon: Sun },
    { value: "system", label: t("settings.system", "System"), icon: Monitor },
  ];
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title={t("settings.appearance", "Appearance")} />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-3">
            {themes.map((x) => (
              <button
                key={x.value}
                type="button"
                onClick={() => {
                  setTheme(x.value);
                  persist({ theme: x.value });
                }}
                className={cn("flex items-center gap-3 rounded-xl border p-4 text-start transition-colors", theme === x.value ? "border-primary bg-primary-soft" : "border-line hover:bg-surface-2")}
              >
                <x.icon className={cn("size-5", theme === x.value ? "text-primary" : "text-muted")} />
                <span className="text-sm font-medium text-fg">{x.label}</span>
              </button>
            ))}
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("settings.language", "Language")} subtitle={t("settings.language_sub", "Arabic switches the whole interface to right-to-left.")} />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-2">
            {([["en", "English"], ["ar", "العربية"]] as [Lang, string][]).map(([value, label]) => (
              <button
                key={value}
                type="button"
                onClick={() => {
                  setLang(value);
                  persist({ lang: value });
                }}
                className={cn("rounded-xl border p-4 text-start text-sm font-medium transition-colors", lang === value ? "border-primary bg-primary-soft text-fg" : "border-line text-fg hover:bg-surface-2")}
              >
                {label}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-medium text-fg">{t("settings.classic", "Classic interface")}</p>
            <p className="text-sm text-muted">{t("settings.classic_sub", "Every original page is still available.")}</p>
          </div>
          <a href="/dashboard"><Button variant="secondary" size="sm" icon={<ExternalLink className="size-4" />}>{t("settings.open_classic", "Open classic")}</Button></a>
        </CardBody>
      </Card>
      {user.demo && <Notice>{t("settings.demo_user", "This is a demo account — data may be reset at any time.")}</Notice>}
    </div>
  );
}

/* ------------------------------------------------------------------ security */

function PasswordCard() {
  const t = useT();
  const toast = useToast();
  const [f, setF] = useState({ current: "", next: "", confirm: "" });
  const mismatch = !!f.confirm && f.next !== f.confirm;
  const save = useMutation({
    mutationFn: () => v2.post("/auth/password", { current_password: f.current, new_password: f.next }),
    onSuccess: () => {
      toast.success(t("settings.pw_ok", "Password updated"));
      setF({ current: "", next: "", confirm: "" });
    },
    onError: (e) => toast.error(e),
  });
  return (
    <Card>
      <CardHeader title={t("settings.password", "Password")} />
      <CardBody>
        <form
          className="grid gap-4 sm:grid-cols-3"
          onSubmit={(e) => {
            e.preventDefault();
            if (!mismatch) save.mutate();
          }}
        >
          <Field label={t("settings.pw_current", "Current password")}><Input type="password" autoComplete="current-password" value={f.current} onChange={(e) => setF({ ...f, current: e.target.value })} /></Field>
          <Field label={t("settings.pw_new", "New password")} hint={t("auth.pw_rule", "At least 8 characters.")}><Input type="password" autoComplete="new-password" value={f.next} onChange={(e) => setF({ ...f, next: e.target.value })} /></Field>
          <Field label={t("settings.pw_confirm", "Confirm new password")} error={mismatch ? t("auth.pw_mismatch", "Passwords do not match") : undefined}><Input type="password" autoComplete="new-password" value={f.confirm} onChange={(e) => setF({ ...f, confirm: e.target.value })} /></Field>
          <div className="flex justify-end sm:col-span-3">
            <Button type="submit" loading={save.isPending} disabled={!f.current || f.next.length < 8 || f.next !== f.confirm}>{t("settings.pw_update", "Update password")}</Button>
          </div>
        </form>
      </CardBody>
    </Card>
  );
}

function TwoFactorCard({ user }: { user: User }) {
  const t = useT();
  const toast = useToast();
  const { refresh } = useAuth();
  const [setup, setSetup] = useState<{ secret: string; uri: string; qr: string } | null>(null);
  const [code, setCode] = useState("");
  const [password, setPassword] = useState("");
  const [busy, setBusy] = useState(false);
  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    try {
      await fn();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  const start = () => run(async () => {
    const r = await v2.post<{ secret: string; uri: string }>("/auth/2fa/setup");
    setSetup({ ...r, qr: await QRCode.toDataURL(r.uri, { margin: 1, width: 200 }) });
    setCode("");
  });
  const enable = () => run(async () => {
    await v2.post("/auth/2fa/enable", { code });
    toast.success(t("settings.2fa_on", "Two-factor authentication is on"));
    setSetup(null);
    setCode("");
    await refresh();
  });
  const disable = () => run(async () => {
    await v2.post("/auth/2fa/disable", { password, code });
    toast.success(t("settings.2fa_off", "Two-factor authentication is off"));
    setPassword("");
    setCode("");
    await refresh();
  });

  return (
    <Card>
      <CardHeader
        title={t("settings.2fa", "Two-factor authentication")}
        subtitle={t("settings.2fa_sub", "Use an authenticator app (Google Authenticator, Authy, 1Password…) at sign-in.")}
        actions={user.totp_enabled ? <Badge tone="up"><ShieldCheck className="size-3.5" />{t("settings.enabled", "Enabled")}</Badge> : <Badge>{t("settings.disabled", "Disabled")}</Badge>}
      />
      <CardBody className="space-y-4">
        {user.totp_enabled ? (
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label={t("settings.pw_current", "Current password")}><Input type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} /></Field>
            <Field label={t("settings.2fa_code", "6-digit code")}><Input inputMode="numeric" maxLength={6} value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
            <div className="flex items-end"><Button variant="danger" loading={busy} disabled={!password || code.length !== 6} onClick={disable}>{t("settings.2fa_disable", "Turn off")}</Button></div>
          </div>
        ) : setup ? (
          <div className="grid gap-6 sm:grid-cols-[auto_1fr]">
            <img src={setup.qr} alt={t("settings.2fa_qr", "QR code for your authenticator app")} className="size-44 rounded-xl border border-line bg-white p-2" />
            <div className="space-y-3">
              <ol className="list-decimal space-y-1 ps-5 text-sm text-fg">
                <li>{t("settings.2fa_s1", "Scan the QR code with your authenticator app.")}</li>
                <li>{t("settings.2fa_s2", "Or enter this key manually:")} <code className="rounded bg-surface-2 px-1.5 py-0.5 font-mono text-xs break-all">{setup.secret}</code></li>
                <li>{t("settings.2fa_s3", "Type the 6-digit code the app shows.")}</li>
              </ol>
              <div className="flex flex-wrap items-end gap-2">
                <Field label={t("settings.2fa_code", "6-digit code")}><Input inputMode="numeric" maxLength={6} className="w-36" value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, ""))} /></Field>
                <Button loading={busy} disabled={code.length !== 6} onClick={enable}>{t("settings.2fa_verify", "Verify & enable")}</Button>
                <Button variant="ghost" onClick={() => setSetup(null)}>{t("common.cancel", "Cancel")}</Button>
              </div>
            </div>
          </div>
        ) : (
          <Button icon={<KeyRound className="size-4" />} loading={busy} onClick={start}>{t("settings.2fa_setup", "Set up 2FA")}</Button>
        )}
      </CardBody>
    </Card>
  );
}

const EVENT_LABELS: Record<string, string> = {
  login: "Sign-in", logout: "Sign-out", register: "Account created", password_change: "Password changed",
  password_reset: "Password reset", "2fa_enabled": "2FA enabled", "2fa_disabled": "2FA disabled",
};

function SecurityTab({ user }: { user: User }) {
  const t = useT();
  const toast = useToast();
  const { setUser } = useAuth();
  const log = useQuery({ queryKey: ["security-log"], queryFn: () => v2.get<LoginEvent[]>("/auth/security-log") });
  const ip = useMutation({
    mutationFn: (v: boolean) => v2.patch<User>("/auth/me", { ip_check: v }),
    onSuccess: (u) => {
      setUser(u);
      toast.success(u.ip_check ? t("settings.ip_on", "New-location check enabled") : t("settings.ip_off", "New-location check disabled"));
    },
    onError: (e) => toast.error(e),
  });
  return (
    <div className="space-y-5">
      <PasswordCard />
      <TwoFactorCard user={user} />
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-4">
          <div className="max-w-xl">
            <p className="text-sm font-medium text-fg">{t("settings.ip", "Email code on new IP address")}</p>
            <p className="text-sm text-muted">{t("settings.ip_sub", "When you sign in from an unfamiliar network we email you a one-time code first.")}</p>
          </div>
          <Switch checked={user.ip_check} disabled={ip.isPending} onChange={(v) => ip.mutate(v)} />
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("settings.log", "Security activity")} subtitle={t("settings.log_sub", "The last 100 sign-ins and account changes.")} />
        {log.isLoading ? <Skeleton className="m-4 h-40" /> : (
          <Table>
            <thead><tr><Th>{t("settings.event", "Event")}</Th><Th>{t("settings.result", "Result")}</Th><Th>IP</Th><Th>{t("settings.device", "Device")}</Th><Th align="end">{t("history.date", "Date")}</Th></tr></thead>
            <tbody>
              {(log.data ?? []).map((e) => (
                <tr key={e.id}>
                  <Td className="text-fg">{t(`settings.ev.${e.event}`, EVENT_LABELS[e.event] ?? e.event)}</Td>
                  <Td>{e.success ? <Badge tone="up">{t("settings.ok", "Success")}</Badge> : <Badge tone="down">{t("settings.failed", "Failed")}</Badge>}</Td>
                  <Td className="num text-muted">{e.ip ?? "—"}</Td>
                  <Td className="max-w-72 truncate text-muted" >{e.user_agent ?? "—"}</Td>
                  <Td align="end" className="text-muted">{fmtDateTime(e.created_at)}</Td>
                </tr>
              ))}
              {!log.data?.length && <tr><Td className="text-muted">{t("settings.log_empty", "No activity recorded yet.")}</Td></tr>}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ notification channels */

interface Channels { webhook_url: string; webhook_enabled: boolean; telegram_chat_id: string; telegram_enabled: boolean; telegram_available: boolean }

function NotificationsTab() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ["channels"], queryFn: () => v2.get<Channels>("/notifications/channels") });
  const [f, setF] = useState<Channels | null>(null);
  useEffect(() => {
    if (q.data) setF(q.data);
  }, [q.data]);
  const save = useMutation({
    mutationFn: (c: Channels) => v2.put<Channels>("/notifications/channels", c),
    onSuccess: (c) => {
      qc.setQueryData(["channels"], c);
      toast.success(t("settings.saved", "Settings saved"));
    },
    onError: (e) => toast.error(e),
  });
  const test = useMutation({ mutationFn: () => v2.post("/notifications/test"), onSuccess: () => toast.success(t("settings.test_sent", "Test notification sent")), onError: (e) => toast.error(e) });
  if (!f) return <Skeleton className="h-64" />;
  return (
    <div className="space-y-5">
      <Notice>{t("settings.ch_note", "In-app notifications are always on. Channels below receive a copy of every trade, bot and alert notification.")}</Notice>
      <Card>
        <CardHeader title={t("settings.webhook", "Discord / Slack webhook")} actions={<Switch checked={f.webhook_enabled} onChange={(v) => setF({ ...f, webhook_enabled: v })} />} />
        <CardBody>
          <Field label={t("settings.webhook_url", "Webhook URL")} hint={t("settings.webhook_hint", "Create an incoming webhook in a Discord channel or Slack app and paste its https:// URL.")}>
            <Input value={f.webhook_url} onChange={(e) => setF({ ...f, webhook_url: e.target.value })} placeholder="https://discord.com/api/webhooks/…" />
          </Field>
        </CardBody>
      </Card>
      <Card>
        <CardHeader title="Telegram" actions={<Switch checked={f.telegram_enabled} disabled={!f.telegram_available} onChange={(v) => setF({ ...f, telegram_enabled: v })} />} />
        <CardBody className="space-y-3">
          {!f.telegram_available && <Notice tone="warning">{t("settings.tg_off", "Telegram is not configured on this server (TELEGRAM_BOT_TOKEN).")}</Notice>}
          <Field label={t("settings.tg_chat", "Chat ID")} hint={t("settings.tg_hint", "Start a chat with the PulseTrade bot, then paste your numeric chat id.")}>
            <Input inputMode="numeric" value={f.telegram_chat_id} disabled={!f.telegram_available} onChange={(e) => setF({ ...f, telegram_chat_id: e.target.value })} />
          </Field>
        </CardBody>
      </Card>
      <div className="flex flex-wrap justify-end gap-2">
        <Button variant="secondary" icon={<Send className="size-4" />} loading={test.isPending} onClick={() => test.mutate()}>{t("settings.test", "Send test")}</Button>
        <Button loading={save.isPending} onClick={() => save.mutate(f)}>{t("common.save", "Save")}</Button>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ billing */

interface Invoice { invoice_id: string; amount_due: number; status: string; created: number; paid: boolean; currency: string; url: string | null }

function BillingTab() {
  const t = useT();
  const billing = useQuery({
    queryKey: ["billing"],
    queryFn: () => v2.get<{ plan: Plan | null; sub_date: string | null; expires: string | null; in_good_standing: boolean; usage: { bots: number; smart_trades: number } }>("/billing"),
  });
  const invoices = useQuery({
    queryKey: ["invoices"],
    queryFn: () => request<{ invoices: Invoice[] }>("/api/v1/get_subscriptions_and_invoices", { method: "POST", body: {} }).then((r) => r.invoices).catch(() => [] as Invoice[]),
    staleTime: 5 * 60_000,
  });
  const b = billing.data;
  const lim = (n?: number) => (n === undefined ? "—" : n >= 1e8 ? "∞" : n);
  return (
    <div className="space-y-5">
      <Card>
        <CardHeader title={t("pricing.your_plan", "Your plan")} actions={<Link to="/pricing"><Button size="sm">{t("settings.change_plan", "Change plan")}</Button></Link>} />
        <CardBody>
          {!b ? <Skeleton className="h-20" /> : (
            <div className="grid gap-4 sm:grid-cols-4">
              <div><p className="text-xs text-muted">{t("settings.plan", "Plan")}</p><p className="text-lg font-semibold text-fg capitalize">{b.plan?.type ?? "free"}</p></div>
              <div><p className="text-xs text-muted">{t("pricing.renews", "Renews / expires")}</p><p className="text-sm text-fg">{b.expires ? fmtDate(b.expires) : "—"}</p></div>
              <div><p className="text-xs text-muted">{t("settings.bots_used", "Active bots")}</p><p className="num text-sm text-fg">{b.usage.bots} / {lim(b.plan?.max_bots)}</p></div>
              <div><p className="text-xs text-muted">{t("settings.smart_used", "Active smart trades")}</p><p className="num text-sm text-fg">{b.usage.smart_trades} / {lim(b.plan?.max_sma)}</p></div>
            </div>
          )}
          {b && !b.in_good_standing && <Notice tone="warning" className="mt-4">{t("pricing.lapsed", "Your subscription has lapsed. Renew it to keep trading features.")}</Notice>}
        </CardBody>
      </Card>
      <Card>
        <CardHeader title={t("settings.invoices", "Invoices")} />
        {invoices.isLoading ? <Skeleton className="m-4 h-24" /> : !invoices.data?.length ? (
          <p className="px-5 py-6 text-sm text-muted">{t("settings.no_invoices", "No invoices yet.")}</p>
        ) : (
          <Table>
            <thead><tr><Th>{t("history.date", "Date")}</Th><Th align="end">{t("settings.amount", "Amount")}</Th><Th>{t("settings.status", "Status")}</Th><Th align="end" /></tr></thead>
            <tbody>
              {invoices.data.map((i) => (
                <tr key={i.invoice_id}>
                  <Td>{fmtDate(i.created)}</Td>
                  <Td align="end" className="num">{fmtUsd(i.amount_due / 100)} <span className="text-xs text-muted uppercase">{i.currency}</span></Td>
                  <Td>{i.paid ? <Badge tone="up">{t("settings.paid", "Paid")}</Badge> : <Badge>{i.status}</Badge>}</Td>
                  <Td align="end">{i.url && <a href={i.url} target="_blank" rel="noreferrer" className="text-sm text-primary hover:underline">{t("settings.view", "View")}</a>}</Td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Card>
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export default function Settings() {
  const t = useT();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const tabs: { value: Tab; label: ReactNode }[] = [
    { value: "profile", label: <span className="flex items-center gap-1.5"><UserIcon className="size-4" />{t("settings.profile", "Profile")}</span> },
    { value: "preferences", label: <span className="flex items-center gap-1.5"><Palette className="size-4" />{t("settings.preferences", "Preferences")}</span> },
    { value: "security", label: <span className="flex items-center gap-1.5"><ShieldCheck className="size-4" />{t("settings.security", "Security")}</span> },
    { value: "notifications", label: <span className="flex items-center gap-1.5"><BellRing className="size-4" />{t("settings.notifications", "Notifications")}</span> },
    { value: "billing", label: <span className="flex items-center gap-1.5"><CreditCard className="size-4" />{t("settings.billing", "Billing")}</span> },
  ];
  const raw = params.get("tab") as Tab | null;
  const tab: Tab = raw && tabs.some((x) => x.value === raw) ? raw : "profile";
  const setTab = (v: Tab) => setParams(v === "profile" ? {} : { tab: v }, { replace: true });
  if (!user) return null;
  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <PageHeader icon={<SettingsIcon className="size-5" />} title={t("nav.settings", "Settings")} subtitle={user.email} />
      <Tabs value={tab} onChange={setTab} tabs={tabs} />
      {tab === "profile" && <ProfileTab user={user} />}
      {tab === "preferences" && <PreferencesTab user={user} />}
      {tab === "security" && <SecurityTab user={user} />}
      {tab === "notifications" && <NotificationsTab />}
      {tab === "billing" && <BillingTab />}
      <p className="text-center text-xs text-muted">
        {t("settings.v1_note", "Looking for the classic settings?")} <a className="text-primary hover:underline" href="/user/setting">{t("settings.open_classic", "Open classic")}</a>
      </p>
    </div>
  );
}
