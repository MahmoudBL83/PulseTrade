import { useState } from "react";
import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { Check, CreditCard, Gem } from "lucide-react";
import { useAuth } from "../context/auth";
import { useToast } from "../context/toast";
import { useI18n, useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import type { Plan } from "../lib/types";
import { fmtDate, fmtUsd } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Button, Card, PageHeader, Skeleton, Notice } from "../components/ui";

const UNLIMITED = 1e8;

export function PlanCards({ plans, current, onChoose, busy }: { plans: Plan[]; current?: number | null; onChoose?: (p: Plan) => void; busy?: number | null }) {
  const t = useT();
  const { lang } = useI18n();
  const best = plans.length >= 3 ? plans[Math.floor(plans.length / 2)]?.id : undefined;
  return (
    <div className={cn("grid gap-4", plans.length >= 3 ? "md:grid-cols-3" : "md:grid-cols-2")}>
      {plans.map((p) => {
        const isCurrent = current === p.id;
        const name = (lang === "ar" && p.type_ar) || p.type;
        const free = !p.price;
        return (
          <Card key={p.id} className={cn("relative flex flex-col p-6", p.id === best && "border-primary")}>
            {p.id === best && <Badge tone="primary" className="absolute -top-2.5 start-6">{t("pricing.popular", "Most popular")}</Badge>}
            <div className="flex items-center gap-2">
              <Gem className="size-5 text-primary" />
              <h3 className="text-lg font-semibold text-fg capitalize">{name}</h3>
            </div>
            <p className="mt-4">
              <span className="num text-3xl font-bold text-fg">{free ? t("pricing.free", "Free") : fmtUsd(p.price ?? 0, 0)}</span>
              {!free && <span className="text-sm text-muted"> / {t("pricing.month", "month")}</span>}
            </p>
            {!!p.trial_days && <p className="mt-1 text-sm text-up">{t("pricing.trial", "{n}-day free trial", { n: p.trial_days })}</p>}
            <ul className="mt-6 flex-1 space-y-2.5 text-sm">
              {[
                p.max_bots >= UNLIMITED ? t("pricing.unl_bots", "Unlimited DCA bots") : t("pricing.bots", "{n} active DCA bots", { n: p.max_bots }),
                p.max_sma >= UNLIMITED ? t("pricing.unl_smart", "Unlimited smart trades") : t("pricing.smart", "{n} smart trades", { n: p.max_sma }),
                t("pricing.paper", "Paper trading & backtesting"),
                t("pricing.alerts", "Price alerts & watchlist"),
                t("pricing.analytics", "Portfolio analytics"),
              ].map((f) => (
                <li key={f} className="flex items-start gap-2 text-fg"><Check className="mt-0.5 size-4 shrink-0 text-up" />{f}</li>
              ))}
            </ul>
            <div className="mt-6">
              {onChoose ? (
                <Button className="w-full" variant={isCurrent ? "secondary" : "primary"} disabled={isCurrent} loading={busy === p.id} onClick={() => onChoose(p)}>
                  {isCurrent ? t("pricing.current", "Current plan") : free ? t("pricing.downgrade", "Switch to free") : t("pricing.choose", "Choose plan")}
                </Button>
              ) : (
                <Link to="/register"><Button className="w-full" variant={p.id === best ? "primary" : "secondary"}>{t("landing.cta", "Start for free")}</Button></Link>
              )}
            </div>
          </Card>
        );
      })}
    </div>
  );
}

export default function Pricing() {
  const t = useT();
  const { user, meta, refresh } = useAuth();
  const toast = useToast();
  const [busy, setBusy] = useState<number | null>(null);
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => v2.get<Plan[]>("/plans") });
  const billing = useQuery({
    queryKey: ["billing"],
    queryFn: () => v2.get<{ plan: Plan | null; expires: string | null; in_good_standing: boolean; usage: { bots: number; smart_trades: number } }>("/billing"),
    enabled: !!user,
  });

  const choose = async (p: Plan) => {
    setBusy(p.id);
    try {
      const priceId = p.price ? p.stripe_id : null;
      if (p.price && !priceId) throw new Error(t("pricing.not_ready", "This plan is not available for purchase yet."));
      const endpoint = meta?.features.stripe || !meta?.features.tap ? "/api/v1/create_checkout_session" : "/api/v1/create_checkout_session_tap";
      const res = await v1.post<{ ok: boolean; url?: string; message: string }>(endpoint, { price_id: priceId ?? "None" });
      if (res.url) window.location.href = res.url;
      else {
        toast.success(res.message);
        await refresh();
        billing.refetch();
      }
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(null);
    }
  };

  return (
    <div>
      <PageHeader icon={<CreditCard className="size-5" />} title={t("pricing.title", "Plans")} subtitle={t("pricing.subtitle", "Upgrade any time. Paid plans renew monthly.")} />
      {user && billing.data && (
        <Card className="mb-6 flex flex-wrap items-center gap-x-8 gap-y-3 p-5">
          <div>
            <p className="text-xs text-muted">{t("pricing.your_plan", "Your plan")}</p>
            <p className="text-lg font-semibold text-fg capitalize">{billing.data.plan?.type ?? "free"}</p>
          </div>
          {billing.data.expires && (
            <div>
              <p className="text-xs text-muted">{t("pricing.renews", "Renews / expires")}</p>
              <p className="text-sm text-fg">{fmtDate(billing.data.expires)}</p>
            </div>
          )}
          <div>
            <p className="text-xs text-muted">{t("pricing.usage", "Usage")}</p>
            <p className="num text-sm text-fg">
              {t("pricing.usage_bots", "{a} / {b} bots", { a: billing.data.usage.bots, b: (billing.data.plan?.max_bots ?? 0) >= UNLIMITED ? "∞" : billing.data.plan?.max_bots ?? 0 })} ·{" "}
              {t("pricing.usage_smart", "{a} / {b} smart trades", { a: billing.data.usage.smart_trades, b: (billing.data.plan?.max_sma ?? 0) >= UNLIMITED ? "∞" : billing.data.plan?.max_sma ?? 0 })}
            </p>
          </div>
          {!billing.data.in_good_standing && <Notice tone="warning">{t("pricing.lapsed", "Your subscription has lapsed. Renew it to keep trading features.")}</Notice>}
        </Card>
      )}
      {!meta?.features.stripe && !meta?.features.tap && user && (
        <Notice tone="info" className="mb-6">{t("pricing.no_payments", "Online payments are not configured on this server. An admin can assign plans from the admin panel.")}</Notice>
      )}
      {plans.isLoading ? (
        <div className="grid gap-4 md:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-96" />)}</div>
      ) : (
        plans.data && <PlanCards plans={plans.data} current={user ? billing.data?.plan?.id ?? user.plan?.id : undefined} onChoose={user ? choose : undefined} busy={busy} />
      )}
    </div>
  );
}
