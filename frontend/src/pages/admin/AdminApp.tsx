import { useEffect, useState } from "react";
import { Link, Navigate, NavLink, Route, Routes, useLocation, useNavigate } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeftRight, BookOpen, CreditCard, ExternalLink, LayoutDashboard, LifeBuoy, ListChecks, LogOut, Megaphone, Menu, Plug, Server, Users, X,
} from "lucide-react";
import { useT } from "../../i18n";
import { request, v2 } from "../../lib/api";
import { cn } from "../../lib/utils";
import { Badge, Button, IconButton } from "../../components/ui";
import { Brand, FullPageSpinner, LangToggle, ThemeToggle } from "../../components/layout";
import AdminOverview from "./AdminOverview";
import { AdminTransactions, AdminUsers } from "./AdminUsers";
import { AdminExchanges, AdminPairs, AdminPlans } from "./AdminCatalog";
import { AdminBroadcast, AdminKb, AdminSupport } from "./AdminContent";
import AdminSystem from "./AdminSystem";

const SECTIONS = [
  { to: "/admin", key: "admin.overview", label: "Overview", icon: LayoutDashboard, end: true },
  { to: "/admin/users", key: "admin.users", label: "Users", icon: Users },
  { to: "/admin/transactions", key: "admin.transactions", label: "Transactions", icon: ArrowLeftRight },
  { to: "/admin/support", key: "admin.support", label: "Support desk", icon: LifeBuoy },
  { to: "/admin/kb", key: "admin.kb", label: "Knowledge base", icon: BookOpen },
  { to: "/admin/plans", key: "admin.plans", label: "Plans", icon: CreditCard },
  { to: "/admin/exchanges", key: "admin.exchanges", label: "Exchanges", icon: Plug },
  { to: "/admin/pairs", key: "admin.pairs", label: "Indicator pairs", icon: ListChecks },
  { to: "/admin/broadcast", key: "admin.broadcast", label: "Broadcast", icon: Megaphone },
  { to: "/admin/system", key: "admin.system", label: "System", icon: Server },
];

function AdminNav({ onNavigate }: { onNavigate?: () => void }) {
  const t = useT();
  return (
    <nav className="flex-1 space-y-0.5 overflow-y-auto p-3">
      {SECTIONS.map((s) => (
        <NavLink
          key={s.to}
          to={s.to}
          end={s.end}
          onClick={onNavigate}
          className={({ isActive }) => cn("flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors", isActive ? "bg-primary-soft text-primary" : "text-muted hover:bg-surface-2 hover:text-fg")}
        >
          <s.icon className="size-4 shrink-0" />
          {t(s.key, s.label)}
        </NavLink>
      ))}
    </nav>
  );
}

export default function AdminApp() {
  const t = useT();
  const nav = useNavigate();
  const qc = useQueryClient();
  const loc = useLocation();
  const [drawer, setDrawer] = useState(false);
  const status = useQuery({ queryKey: ["admin", "status"], queryFn: () => v2.get<{ admin: boolean }>("/auth/admin"), staleTime: 60_000 });
  useEffect(() => setDrawer(false), [loc.pathname]);

  if (status.isLoading) return <FullPageSpinner />;
  if (!status.data?.admin) return <Navigate to="/admin/login" replace />;

  const logout = async () => {
    await request("/api/v2/auth/admin/logout", { method: "POST" }).catch(() => undefined);
    qc.removeQueries({ queryKey: ["admin"] });
    nav("/admin/login", { replace: true });
  };
  const brand = (
    <span className="flex items-center gap-2">
      <Brand />
      <Badge tone="primary">{t("admin.badge", "Admin")}</Badge>
    </span>
  );

  return (
    <div className="flex min-h-full">
      <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col border-e border-line bg-surface lg:flex">
        <div className="flex h-14 items-center border-b border-line px-5">{brand}</div>
        <AdminNav />
        <div className="space-y-1 border-t border-line p-3 text-sm">
          <Link to="/dashboard" className="flex items-center gap-2 rounded-lg px-3 py-2 text-muted hover:bg-surface-2 hover:text-fg"><ExternalLink className="size-4" />{t("admin.open_app", "Open the app")}</Link>
          <a href="/admin" className="flex items-center gap-2 rounded-lg px-3 py-2 text-muted hover:bg-surface-2 hover:text-fg"><ExternalLink className="size-4" />{t("admin.classic", "Classic admin")}</a>
        </div>
      </aside>
      {drawer && (
        <div className="fixed inset-0 z-[80] lg:hidden">
          <div className="absolute inset-0 bg-black/60" onClick={() => setDrawer(false)} />
          <aside className="absolute inset-y-0 start-0 flex w-72 max-w-[85vw] flex-col bg-surface shadow-2xl">
            <div className="flex h-14 items-center justify-between border-b border-line px-4">
              {brand}
              <IconButton label={t("common.close", "Close")} onClick={() => setDrawer(false)}><X className="size-4" /></IconButton>
            </div>
            <AdminNav onNavigate={() => setDrawer(false)} />
          </aside>
        </div>
      )}
      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-40 flex h-14 items-center gap-2 border-b border-line bg-surface/90 px-3 backdrop-blur sm:px-4">
          <IconButton label={t("nav.menu", "Menu")} className="lg:hidden" onClick={() => setDrawer(true)}><Menu className="size-5" /></IconButton>
          <span className="lg:hidden">{brand}</span>
          <div className="ms-auto flex items-center gap-1 sm:gap-2">
            <LangToggle />
            <ThemeToggle />
            <Button variant="ghost" size="sm" icon={<LogOut className="size-4" />} onClick={logout}>{t("auth.logout", "Log out")}</Button>
          </div>
        </header>
        <main className="mx-auto w-full max-w-[1600px] flex-1 px-4 py-5 sm:px-6 sm:py-6">
          <Routes>
            <Route index element={<AdminOverview />} />
            <Route path="users" element={<AdminUsers />} />
            <Route path="transactions" element={<AdminTransactions />} />
            <Route path="support" element={<AdminSupport />} />
            <Route path="kb" element={<AdminKb />} />
            <Route path="plans" element={<AdminPlans />} />
            <Route path="exchanges" element={<AdminExchanges />} />
            <Route path="pairs" element={<AdminPairs />} />
            <Route path="broadcast" element={<AdminBroadcast />} />
            <Route path="system" element={<AdminSystem />} />
            <Route path="*" element={<Navigate to="/admin" replace />} />
          </Routes>
        </main>
      </div>
    </div>
  );
}
