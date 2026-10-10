import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, Outlet, useLocation, useNavigate } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight, Bell, BellRing, BookOpen, Bot, Calculator, ChartCandlestick, ChevronDown, CreditCard,
  FlaskConical, Gauge as GaugeIcon, History, LayoutDashboard, LifeBuoy, LogOut, Menu, Moon, NotebookPen, PieChart,
  Plug, Search, Settings, Shield, Star, Sun, Target, Wallet, X, Languages, ExternalLink, Check,
} from "lucide-react";
import { useAuth } from "../context/auth";
import { useTheme } from "../context/theme";
import { useToast } from "../context/toast";
import { useI18n, useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import type { Notification } from "../lib/types";
import { cn, initials, useDebounced } from "../lib/utils";
import { timeAgo } from "../lib/format";
import { parseNotification, useSocketEvent, closeSocket } from "../lib/socket";
import { Avatar, Badge, Button, IconButton, Kbd, Spinner } from "./ui";

/* ------------------------------------------------------------------ nav model */

export interface NavItem {
  to: string;
  key: string;
  label: string;
  icon: typeof LayoutDashboard;
  public?: boolean;
}

export const NAV: { section: string; label: string; items: NavItem[] }[] = [
  {
    section: "trade", label: "Trading", items: [
      { to: "/dashboard", key: "nav.dashboard", label: "Dashboard", icon: LayoutDashboard },
      { to: "/markets", key: "nav.markets", label: "Markets", icon: ChartCandlestick, public: true },
      { to: "/trade", key: "nav.trade", label: "Trade", icon: ArrowLeftRight },
      { to: "/smart-trades", key: "nav.smart", label: "Smart trades", icon: Target },
      { to: "/bots", key: "nav.bots", label: "DCA bots", icon: Bot },
      { to: "/backtest", key: "nav.backtest", label: "Backtest", icon: FlaskConical, public: true },
    ],
  },
  {
    section: "money", label: "Portfolio", items: [
      { to: "/portfolio", key: "nav.portfolio", label: "Portfolio", icon: PieChart },
      { to: "/wallet", key: "nav.wallet", label: "Wallet", icon: Wallet },
      { to: "/history", key: "nav.history", label: "History", icon: History },
      { to: "/exchanges", key: "nav.exchanges", label: "Exchanges", icon: Plug },
    ],
  },
  {
    section: "tools", label: "Tools", items: [
      { to: "/watchlist", key: "nav.watchlist", label: "Watchlist", icon: Star },
      { to: "/alerts", key: "nav.alerts", label: "Price alerts", icon: BellRing },
      { to: "/journal", key: "nav.journal", label: "Journal", icon: NotebookPen },
      { to: "/insights", key: "nav.insights", label: "Market pulse", icon: GaugeIcon, public: true },
      { to: "/tools", key: "nav.tools", label: "Calculators", icon: Calculator, public: true },
    ],
  },
  {
    section: "account", label: "Account", items: [
      { to: "/notifications", key: "nav.notifications", label: "Notifications", icon: Bell },
      { to: "/support", key: "nav.support", label: "Support", icon: LifeBuoy },
      { to: "/kb", key: "nav.kb", label: "Knowledge base", icon: BookOpen, public: true },
      { to: "/pricing", key: "nav.pricing", label: "Plans", icon: CreditCard, public: true },
      { to: "/settings", key: "nav.settings", label: "Settings", icon: Settings },
    ],
  },
];

const sectionKeys: Record<string, string> = { trade: "nav.section.trading", money: "nav.section.portfolio", tools: "nav.section.tools", account: "nav.section.account" };

/* ------------------------------------------------------------------ guards */

export function RequireAuth({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();
  const loc = useLocation();
  if (loading) return <FullPageSpinner />;
  if (!user) return <Navigate to={`/login?next=${encodeURIComponent(loc.pathname + loc.search)}`} replace />;
  return <>{children}</>;
}

export function FullPageSpinner() {
  return (
    <div className="flex h-full min-h-[60vh] items-center justify-center">
      <Spinner className="size-7" />
    </div>
  );
}

/* ------------------------------------------------------------------ popover */

export function Popover({ trigger, children, align = "end", className }: { trigger: (open: boolean, toggle: () => void) => ReactNode; children: (close: () => void) => ReactNode; align?: "start" | "end"; className?: string }) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  return (
    <div ref={ref} className="relative">
      {trigger(open, () => setOpen((o) => !o))}
      {open && (
        <div className={cn("absolute top-full z-50 mt-2 min-w-56 rounded-xl border border-line bg-surface p-1 shadow-xl", align === "end" ? "end-0" : "start-0", className)}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}

export function MenuItem({ icon: Icon, children, onClick, to, danger, external }: { icon?: typeof Bell; children: ReactNode; onClick?: () => void; to?: string; danger?: boolean; external?: boolean }) {
  const cls = cn("flex w-full items-center gap-2.5 rounded-lg px-3 py-2 text-start text-sm transition-colors hover:bg-surface-2", danger ? "text-down" : "text-fg");
  const content = (
    <>
      {Icon && <Icon className="size-4 shrink-0 text-muted" />}
      <span className="flex-1">{children}</span>
      {external && <ExternalLink className="size-3.5 text-muted" />}
    </>
  );
  if (to && external) return <a href={to} className={cls} onClick={onClick}>{content}</a>;
  if (to) return <Link to={to} className={cls} onClick={onClick}>{content}</Link>;
  return <button type="button" className={cls} onClick={onClick}>{content}</button>;
}

/* ------------------------------------------------------------------ brand */

export function Brand({ compact }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2">
      <span className="flex size-8 items-center justify-center rounded-lg bg-primary text-primary-fg">
        <svg viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={2.4} strokeLinecap="round" strokeLinejoin="round" aria-hidden>
          <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />
        </svg>
      </span>
      {!compact && <span className="text-base font-semibold tracking-tight text-fg">PulseTrade</span>}
    </span>
  );
}

/* ------------------------------------------------------------------ toggles */

export function ThemeToggle() {
  const { resolved, setTheme } = useTheme();
  const t = useT();
  return (
    <IconButton label={t("common.toggle_theme", "Toggle theme")} onClick={() => setTheme(resolved === "dark" ? "light" : "dark")}>
      {resolved === "dark" ? <Sun className="size-4" /> : <Moon className="size-4" />}
    </IconButton>
  );
}

export function LangToggle({ onChange }: { onChange?: (l: "en" | "ar") => void }) {
  const { lang, setLang } = useI18n();
  return (
    <IconButton
      label={lang === "ar" ? "English" : "العربية"}
      onClick={() => {
        const next = lang === "ar" ? "en" : "ar";
        setLang(next);
        onChange?.(next);
      }}
    >
      <Languages className="size-4" />
    </IconButton>
  );
}

/* ------------------------------------------------------------------ command palette */

function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const t = useT();
  const nav = useNavigate();
  const [q, setQ] = useState("");
  const [idx, setIdx] = useState(0);
  const dq = useDebounced(q, 200);
  const { user } = useAuth();
  const symbols = useQuery({
    queryKey: ["symbols-search", dq],
    queryFn: () => v2.get<string[]>("/market/symbols", { q: dq, quote: "USDT", limit: 8 }),
    enabled: open && dq.length >= 2,
    staleTime: 60_000,
  });
  const pages = useMemo(() => NAV.flatMap((s) => s.items).filter((i) => user || i.public), [user]);
  const results = useMemo(() => {
    const needle = q.toLowerCase();
    const pg = pages
      .filter((p) => !needle || t(p.key, p.label).toLowerCase().includes(needle) || p.label.toLowerCase().includes(needle))
      .slice(0, 8)
      .map((p) => ({ id: p.to, label: t(p.key, p.label), hint: t("palette.page", "Page"), go: () => nav(p.to) }));
    const sy = (symbols.data ?? []).map((s) => ({ id: s, label: s, hint: t("palette.market", "Market"), go: () => nav(`/markets/${s.replace("/", "-")}`) }));
    return [...sy, ...pg];
  }, [q, pages, symbols.data, nav, t]);

  useEffect(() => {
    if (open) {
      setQ("");
      setIdx(0);
    }
  }, [open]);
  useEffect(() => setIdx(0), [dq]);
  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[95] flex items-start justify-center bg-black/60 p-4 pt-[12vh] backdrop-blur-sm" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className="w-full max-w-lg overflow-hidden rounded-2xl border border-line bg-surface shadow-2xl" role="dialog" aria-label={t("palette.title", "Search")}>
        <div className="flex items-center gap-2 border-b border-line px-4">
          <Search className="size-4 text-muted" />
          <input
            autoFocus
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") onClose();
              if (e.key === "ArrowDown") { e.preventDefault(); setIdx((i) => Math.min(i + 1, results.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setIdx((i) => Math.max(i - 1, 0)); }
              if (e.key === "Enter" && results[idx]) { results[idx].go(); onClose(); }
            }}
            placeholder={t("palette.placeholder", "Search pages or markets (e.g. BTC)…")}
            className="h-12 flex-1 bg-transparent text-sm text-fg placeholder:text-muted focus:outline-none"
          />
          <Kbd>Esc</Kbd>
        </div>
        <ul className="max-h-80 overflow-y-auto p-1">
          {results.map((r, i) => (
            <li key={r.id}>
              <button
                type="button"
                onMouseEnter={() => setIdx(i)}
                onClick={() => { r.go(); onClose(); }}
                className={cn("flex w-full items-center justify-between rounded-lg px-3 py-2 text-start text-sm", i === idx ? "bg-surface-2 text-fg" : "text-fg")}
              >
                <span>{r.label}</span>
                <span className="text-xs text-muted">{r.hint}</span>
              </button>
            </li>
          ))}
          {!results.length && <li className="px-3 py-6 text-center text-sm text-muted">{t("palette.empty", "No results")}</li>}
        </ul>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ notifications */

function NotificationBell() {
  const t = useT();
  const { user, refresh, meta } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  const list = useQuery({
    queryKey: ["notifications", "latest"],
    queryFn: () => v2.raw<{ data: Notification[]; unread: number }>("/notifications", { limit: 8 }),
    enabled: !!user,
    refetchInterval: 60_000,
  });
  useSocketEvent<string>(
    "new_notification",
    (raw) => {
      const n = parseNotification(raw);
      if (user && String(n.userId) !== String(user.id)) return;
      toast.info(n.text, n.type && n.type !== "system" ? n.type : undefined);
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    !!user && meta?.features.realtime !== false,
  );
  const unread = list.data?.unread ?? user?.unread_notifications ?? 0;
  return (
    <Popover
      trigger={(_, toggle) => (
        <IconButton label={t("nav.notifications", "Notifications")} onClick={toggle} className="relative">
          <Bell className="size-4" />
          {unread > 0 && <span className="num absolute -top-0.5 -end-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-down px-1 text-[10px] font-semibold text-white">{unread > 99 ? "99+" : unread}</span>}
        </IconButton>
      )}
      className="w-[min(22rem,calc(100vw-2rem))] p-0"
    >
      {(close) => (
        <div>
          <div className="flex items-center justify-between border-b border-line px-4 py-2.5">
            <span className="text-sm font-semibold">{t("nav.notifications", "Notifications")}</span>
            <button
              type="button"
              className="text-xs text-primary hover:underline"
              onClick={async () => {
                await v2.post("/notifications/read");
                qc.invalidateQueries({ queryKey: ["notifications"] });
                refresh();
              }}
            >
              {t("notifications.mark_all", "Mark all read")}
            </button>
          </div>
          <ul className="max-h-96 overflow-y-auto">
            {(list.data?.data ?? []).map((n) => (
              <li key={n.id} className={cn("border-b border-line/60 px-4 py-2.5 last:border-0", !n.read && "bg-primary-soft/40")}>
                <p className="text-sm text-fg">{n.content}</p>
                <p className="mt-0.5 text-xs text-muted">
                  {n.type && n.type !== "system" ? `${n.type} · ` : ""}
                  {timeAgo(n.date)}
                </p>
              </li>
            ))}
            {list.data && !list.data.data.length && <li className="px-4 py-8 text-center text-sm text-muted">{t("notifications.empty", "You're all caught up")}</li>}
          </ul>
          <div className="border-t border-line p-1">
            <MenuItem to="/notifications" onClick={close}>{t("notifications.view_all", "View all notifications")}</MenuItem>
          </div>
        </div>
      )}
    </Popover>
  );
}

/* ------------------------------------------------------------------ exchange switcher */

function ExchangeSwitcher() {
  const t = useT();
  const { user, refresh } = useAuth();
  const qc = useQueryClient();
  const toast = useToast();
  if (!user) return null;
  const active = user.exchanges.find((e) => e.isActive);
  return (
    <Popover
      align="start"
      trigger={(_, toggle) => (
        <button type="button" onClick={toggle} className="flex h-9 items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 text-sm text-fg hover:bg-surface-3">
          <Plug className="size-4 text-muted" />
          <span className="max-w-28 truncate">{active ? (active.paper ? t("exchanges.paper", "Paper") : active.name) : t("exchanges.none", "No exchange")}</span>
          <ChevronDown className="size-3.5 text-muted" />
        </button>
      )}
    >
      {(close) => (
        <div className="w-60">
          {user.exchanges.map((e) => (
            <button
              key={e.id}
              type="button"
              className="flex w-full items-center justify-between rounded-lg px-3 py-2 text-sm hover:bg-surface-2"
              onClick={async () => {
                close();
                try {
                  await v1.post("/api/v1/fav_exchange/", { exchange_name: e.name });
                  await refresh();
                  qc.invalidateQueries();
                } catch (err) {
                  toast.error(err);
                }
              }}
            >
              <span className="flex items-center gap-2 capitalize">
                {e.paper ? t("exchanges.paper_long", "Paper trading") : e.name}
                {e.demo && <Badge tone="info">testnet</Badge>}
              </span>
              {e.isActive && <Check className="size-4 text-primary" />}
            </button>
          ))}
          <div className="mt-1 border-t border-line pt-1">
            <MenuItem icon={Plug} to="/exchanges" onClick={close}>{t("exchanges.manage", "Manage exchanges")}</MenuItem>
          </div>
        </div>
      )}
    </Popover>
  );
}

/* ------------------------------------------------------------------ user menu */

function UserMenu() {
  const t = useT();
  const { user, logout } = useAuth();
  const nav = useNavigate();
  if (!user) return null;
  const name = [user.firstName, user.lastName].filter(Boolean).join(" ") || user.email;
  return (
    <Popover
      trigger={(_, toggle) => (
        <button type="button" onClick={toggle} className="flex items-center gap-2 rounded-lg p-1 hover:bg-surface-2" aria-label={t("nav.account", "Account")}>
          <Avatar src={user.img} name={initials(user.firstName, user.lastName, user.email)} size={30} />
        </button>
      )}
    >
      {(close) => (
        <div className="w-64">
          <div className="px-3 py-2">
            <p className="truncate text-sm font-medium text-fg">{name}</p>
            <p className="truncate text-xs text-muted">{user.email}</p>
            {user.plan && <Badge tone="primary" className="mt-2 capitalize">{user.plan.type}</Badge>}
          </div>
          <div className="my-1 border-t border-line" />
          <MenuItem icon={Settings} to="/settings" onClick={close}>{t("nav.settings", "Settings")}</MenuItem>
          <MenuItem icon={CreditCard} to="/pricing" onClick={close}>{t("nav.pricing", "Plans")}</MenuItem>
          <MenuItem icon={ExternalLink} to="/dashboard/" external onClick={close}>{t("nav.classic", "Classic interface")}</MenuItem>
          {user.is_admin && <MenuItem icon={Shield} to="/admin" onClick={close}>{t("nav.admin", "Admin")}</MenuItem>}
          <div className="my-1 border-t border-line" />
          <MenuItem
            icon={LogOut}
            danger
            onClick={async () => {
              close();
              closeSocket();
              await logout();
              nav("/login");
            }}
          >
            {t("auth.logout", "Log out")}
          </MenuItem>
        </div>
      )}
    </Popover>
  );
}

/* ------------------------------------------------------------------ sidebar */

function Sidebar({ onNavigate }: { onNavigate?: () => void }) {
  const t = useT();
  const { user } = useAuth();
  return (
    <nav className="flex h-full flex-col gap-5 overflow-y-auto px-3 py-4" aria-label={t("nav.main", "Main")}>
      {NAV.map((sec) => {
        const items = sec.items.filter((i) => user || i.public);
        if (!items.length) return null;
        return (
          <div key={sec.section}>
            <p className="mb-1.5 px-3 text-[11px] font-semibold tracking-wider text-muted uppercase">{t(sectionKeys[sec.section], sec.label)}</p>
            <ul className="space-y-0.5">
              {items.map((it) => (
                <li key={it.to}>
                  <NavLink
                    to={it.to}
                    onClick={onNavigate}
                    className={({ isActive }) =>
                      cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "bg-primary-soft text-primary" : "text-muted hover:bg-surface-2 hover:text-fg")
                    }
                  >
                    <it.icon className="size-4 shrink-0" />
                    {t(it.key, it.label)}
                  </NavLink>
                </li>
              ))}
            </ul>
          </div>
        );
      })}
    </nav>
  );
}

/* ------------------------------------------------------------------ app shell */

export function AppShell() {
  const t = useT();
  const { user, meta, setUser } = useAuth();
  const [drawer, setDrawer] = useState(false);
  const [palette, setPalette] = useState(false);
  const loc = useLocation();

  useEffect(() => setDrawer(false), [loc.pathname]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPalette((p) => !p);
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);

  const savePref = (key: "lang" | "theme", value: string) => {
    if (!user) return;
    v2.patch<typeof user>("/auth/me", { preferences: { [key]: value } }).then(setUser).catch(() => undefined);
  };

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-e border-line bg-surface lg:flex">
        <Link to={user ? "/dashboard" : "/"} className="flex h-14 items-center border-b border-line px-5">
          <Brand />
        </Link>
        <Sidebar />
      </aside>

      {drawer && (
        <div className="fixed inset-0 z-[80] lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 start-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              <Brand />
              <IconButton label={t("common.close", "Close")} onClick={() => setDrawer(false)}>
                <X className="size-4" />
              </IconButton>
            </div>
            <Sidebar onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-line bg-surface/90 px-3 backdrop-blur sm:px-4">
          <IconButton label={t("nav.menu", "Menu")} className="lg:hidden" onClick={() => setDrawer(true)}>
            <Menu className="size-5" />
          </IconButton>
          <Link to="/" className="lg:hidden">
            <Brand compact />
          </Link>
          <button
            type="button"
            onClick={() => setPalette(true)}
            className="ms-1 hidden h-9 w-full max-w-xs items-center gap-2 rounded-lg border border-line bg-surface-2 px-3 text-sm text-muted hover:text-fg md:flex"
          >
            <Search className="size-4" />
            <span className="flex-1 text-start">{t("palette.search", "Search…")}</span>
            <Kbd>Ctrl K</Kbd>
          </button>
          <IconButton label={t("palette.search", "Search…")} className="md:hidden" onClick={() => setPalette(true)}>
            <Search className="size-4" />
          </IconButton>
          <div className="ms-auto flex items-center gap-1 sm:gap-2">
            {meta?.demo && <Badge tone="info" className="hidden sm:inline-flex">{t("common.demo", "Demo")}</Badge>}
            {user && <ExchangeSwitcher />}
            <LangToggle onChange={(l) => savePref("lang", l)} />
            <ThemeToggle />
            {user ? (
              <>
                <NotificationBell />
                <UserMenu />
              </>
            ) : (
              <>
                <Link to="/login"><Button variant="ghost" size="sm">{t("auth.login", "Log in")}</Button></Link>
                <Link to="/register" className="hidden sm:block"><Button size="sm">{t("auth.signup", "Sign up")}</Button></Link>
              </>
            )}
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={palette} onClose={() => setPalette(false)} />
    </div>
  );
}

/* ------------------------------------------------------------------ public shell */

export function PublicShell() {
  const t = useT();
  const { user } = useAuth();
  return (
    <div className="flex min-h-full flex-col">
      <header className="sticky top-0 z-40 border-b border-line bg-bg/80 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-6xl items-center gap-4 px-4">
          <Link to="/"><Brand /></Link>
          <nav className="ms-6 hidden items-center gap-1 md:flex">
            {[
              ["/markets", t("nav.markets", "Markets")],
              ["/insights", t("nav.insights", "Market pulse")],
              ["/backtest", t("nav.backtest", "Backtest")],
              ["/pricing", t("nav.pricing", "Plans")],
              ["/kb", t("nav.kb", "Knowledge base")],
            ].map(([to, label]) => (
              <NavLink key={to} to={to} className={({ isActive }) => cn("rounded-lg px-3 py-2 text-sm font-medium", isActive ? "text-fg" : "text-muted hover:text-fg")}>
                {label}
              </NavLink>
            ))}
          </nav>
          <div className="ms-auto flex items-center gap-1 sm:gap-2">
            <LangToggle />
            <ThemeToggle />
            {user ? (
              <Link to="/dashboard"><Button size="sm">{t("nav.dashboard", "Dashboard")}</Button></Link>
            ) : (
              <>
                <Link to="/login"><Button variant="ghost" size="sm">{t("auth.login", "Log in")}</Button></Link>
                <Link to="/register"><Button size="sm">{t("auth.signup", "Sign up")}</Button></Link>
              </>
            )}
          </div>
        </div>
      </header>
      <main className="flex-1">
        <Outlet />
      </main>
      <footer className="border-t border-line">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-6 text-sm text-muted">
          <span>© {new Date().getFullYear()} PulseTrade</span>
          <div className="flex flex-wrap gap-4">
            <a href="/terms-of-service" className="hover:text-fg">{t("legal.terms", "Terms")}</a>
            <a href="/privacy-policy" className="hover:text-fg">{t("legal.privacy", "Privacy")}</a>
            <a href="/docs/" className="hover:text-fg">{t("legal.api", "API docs")}</a>
            <a href="/" className="hover:text-fg">{t("nav.classic", "Classic interface")}</a>
          </div>
        </div>
      </footer>
    </div>
  );
}
