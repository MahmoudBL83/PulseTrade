import { Link } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowRight, BellRing, Bot, FlaskConical, Globe2, LineChart, Lock, PieChart, Target, Wallet } from "lucide-react";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import { useTickers, useMarketExchanges } from "../lib/hooks";
import type { KbPost, Plan } from "../lib/types";
import { fmtDate } from "../lib/format";
import { Button, Card, CoinIcon } from "../components/ui";
import { Change, Price } from "../components/market";
import { PlanCards } from "./Pricing";

export default function Landing() {
  const t = useT();
  const tickers = useTickers("USDT", 12);
  const exchanges = useMarketExchanges();
  const plans = useQuery({ queryKey: ["plans"], queryFn: () => v2.get<Plan[]>("/plans") });
  const posts = useQuery({ queryKey: ["kb-posts", "latest"], queryFn: () => v2.get<KbPost[]>("/kb/posts", { limit: 3 }) });

  const features = [
    { icon: Bot, title: t("landing.f_bots", "DCA bots"), body: t("landing.f_bots_b", "Safety orders, trailing take profit, stop-loss timeouts and indicator conditions — running 24/7.") },
    { icon: Target, title: t("landing.f_smart", "Smart trades"), body: t("landing.f_smart_b", "Multi-level take profits, conditional entries, break-even stops and trailing exits.") },
    { icon: Wallet, title: t("landing.f_paper", "Paper trading"), body: t("landing.f_paper_b", "Practise every feature with a simulated $10,000 account — no API keys needed.") },
    { icon: FlaskConical, title: t("landing.f_backtest", "Backtest & optimise"), body: t("landing.f_backtest_b", "Replay a DCA strategy on historical candles and grid-search the best parameters.") },
    { icon: PieChart, title: t("landing.f_portfolio", "Portfolio analytics"), body: t("landing.f_portfolio_b", "Balances across exchanges with Sharpe, Sortino, drawdown and CAGR.") },
    { icon: BellRing, title: t("landing.f_alerts", "Price alerts"), body: t("landing.f_alerts_b", "In-app, Discord, Slack or Telegram alerts when a market crosses your level.") },
    { icon: Globe2, title: t("landing.f_exchanges", "100+ exchanges"), body: t("landing.f_exchanges_b", "One interface for Binance, OKX, Bybit, KuCoin and more, powered by CCXT.") },
    { icon: Lock, title: t("landing.f_security", "Security first"), body: t("landing.f_security_b", "Encrypted API keys, authenticator-app 2FA, new-IP checks and a login history.") },
  ];

  return (
    <div>
      {/* hero */}
      <section className="relative overflow-hidden border-b border-line">
        <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(60%_50%_at_50%_0%,var(--primary-soft),transparent)]" />
        <div className="relative mx-auto max-w-6xl px-4 py-16 text-center sm:py-24">
          <span className="inline-flex items-center gap-2 rounded-full border border-line bg-surface px-3 py-1 text-xs text-muted">
            <LineChart className="size-3.5 text-primary" />
            {t("landing.badge", "Automated crypto trading, simplified")}
          </span>
          <h1 className="mx-auto mt-5 max-w-3xl text-4xl font-bold tracking-tight text-fg sm:text-6xl">
            {t("landing.title", "Trade smarter with bots that never sleep")}
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base text-muted sm:text-lg">
            {t("landing.subtitle", "PulseTrade connects your exchanges, runs DCA bots and smart trades, and shows your whole portfolio in one place. Start risk-free with paper trading.")}
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link to="/register"><Button size="lg">{t("landing.cta", "Start for free")}<ArrowRight className="size-4 rtl:rotate-180" /></Button></Link>
            <Link to="/markets"><Button size="lg" variant="secondary">{t("landing.explore", "Explore markets")}</Button></Link>
          </div>
        </div>
        {/* live strip */}
        <div className="relative border-t border-line bg-surface/60">
          <div className="mx-auto flex max-w-6xl gap-6 overflow-x-auto px-4 py-3">
            {(tickers.data ?? []).slice(0, 10).map((tk) => (
              <Link key={tk.symbol} to={`/markets/${tk.symbol.replace("/", "-")}`} className="flex shrink-0 items-center gap-2 text-sm">
                <CoinIcon symbol={tk.symbol} size={18} />
                <span className="font-medium text-fg">{tk.symbol.split("/")[0]}</span>
                <Price value={tk.last} className="text-muted" />
                <Change value={tk.percentage} className="text-xs" />
              </Link>
            ))}
          </div>
        </div>
      </section>

      {/* features */}
      <section className="mx-auto max-w-6xl px-4 py-16">
        <h2 className="text-center text-2xl font-semibold tracking-tight text-fg sm:text-3xl">{t("landing.features", "Everything you need to trade on autopilot")}</h2>
        <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {features.map((f) => (
            <Card key={f.title} className="p-5">
              <div className="flex size-10 items-center justify-center rounded-xl bg-primary-soft text-primary"><f.icon className="size-5" /></div>
              <h3 className="mt-4 text-sm font-semibold text-fg">{f.title}</h3>
              <p className="mt-1.5 text-sm text-muted">{f.body}</p>
            </Card>
          ))}
        </div>
      </section>

      {/* exchanges */}
      {!!exchanges.data?.length && (
        <section className="border-y border-line bg-surface/50">
          <div className="mx-auto max-w-6xl px-4 py-10 text-center">
            <p className="text-sm text-muted">{t("landing.exchanges", "Connect the exchanges you already use")}</p>
            <div className="mt-5 flex flex-wrap justify-center gap-3">
              {exchanges.data.map((e) => (
                <span key={e.id} className="rounded-xl border border-line bg-surface px-4 py-2 text-sm font-medium text-fg capitalize">{e.paper ? t("exchanges.paper_long", "Paper trading") : e.id}</span>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* pricing */}
      <section className="mx-auto max-w-6xl px-4 py-16" id="pricing">
        <h2 className="text-center text-2xl font-semibold tracking-tight text-fg sm:text-3xl">{t("landing.pricing", "Simple, transparent plans")}</h2>
        <div className="mt-10">{plans.data && <PlanCards plans={plans.data} />}</div>
      </section>

      {/* blog */}
      {!!posts.data?.length && (
        <section className="mx-auto max-w-6xl px-4 pb-16">
          <div className="mb-6 flex items-end justify-between">
            <h2 className="text-xl font-semibold tracking-tight text-fg">{t("landing.blog", "From the knowledge base")}</h2>
            <Link to="/kb" className="text-sm text-primary hover:underline">{t("common.view_all", "View all")}</Link>
          </div>
          <div className="grid gap-4 md:grid-cols-3">
            {posts.data.map((p) => (
              <Link key={p.id} to={`/kb/${p.id}`}>
                <Card className="h-full overflow-hidden transition-colors hover:border-primary/50">
                  {p.img && <img src={p.img} alt="" loading="lazy" className="h-40 w-full object-cover" />}
                  <div className="p-5">
                    <p className="text-xs text-muted">{fmtDate(p.created_at)}</p>
                    <h3 className="mt-1 font-semibold text-fg">{p.title}</h3>
                    <p className="mt-2 line-clamp-3 text-sm text-muted">{p.excerpt}</p>
                  </div>
                </Card>
              </Link>
            ))}
          </div>
        </section>
      )}

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-4 pb-20">
        <Card className="flex flex-col items-center gap-4 bg-[linear-gradient(135deg,var(--primary-soft),transparent)] p-10 text-center">
          <h2 className="text-2xl font-semibold text-fg">{t("landing.cta_title", "Ready when you are")}</h2>
          <p className="max-w-xl text-muted">{t("landing.cta_body", "Create a free account and get a paper-trading wallet instantly. Connect a real exchange whenever you like.")}</p>
          <Link to="/register"><Button size="lg">{t("landing.cta", "Start for free")}</Button></Link>
        </Card>
      </section>
    </div>
  );
}
