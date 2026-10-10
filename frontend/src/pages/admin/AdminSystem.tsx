import { useState, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ExternalLink, Play, Server } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { v2 } from "../../lib/api";
import { timeAgo } from "../../lib/format";
import { Badge, Button, Card, CardBody, CardHeader, Dot, PageHeader, Skeleton } from "../../components/ui";

interface SystemInfo {
  engine: string; market_data: string; reference_exchange: string; db_dialect: string; tables: number;
  mail_configured: boolean; stripe_configured: boolean; tap_configured: boolean; cron_secret: boolean; admin_totp: boolean;
  vercel: boolean; demo: boolean; build: string; scheduler_running: boolean;
}

interface StreamStatus { enabled: boolean; running: boolean; exchange: string | null; symbols: string[]; updates: number; last_update: number | null; last_error: string | null; started_at: number | null }

function Row({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 border-b border-line/60 py-2.5 text-sm last:border-0">
      <span className="text-muted">{label}</span>
      <span className="text-end text-fg">{children}</span>
    </div>
  );
}

function Flag({ on, onLabel, offLabel }: { on: boolean; onLabel: string; offLabel: string }) {
  return <span className="inline-flex items-center gap-1.5"><Dot tone={on ? "up" : "neutral"} />{on ? onLabel : offLabel}</span>;
}

export default function AdminSystem() {
  const t = useT();
  const toast = useToast();
  const sys = useQuery({ queryKey: ["admin", "system"], queryFn: () => v2.get<SystemInfo>("/admin/system") });
  const stream = useQuery({ queryKey: ["admin", "stream"], queryFn: () => v2.get<StreamStatus>("/market/stream"), refetchInterval: 15_000 });
  const [result, setResult] = useState<unknown>(null);
  const tick = useMutation({
    mutationFn: () => v2.post<unknown>("/admin/engine/tick"),
    onSuccess: (r) => {
      setResult(r);
      toast.success(t("admin.tick_ok", "Engine tick finished"));
    },
    onError: (e) => toast.error(e),
  });
  const on = t("admin.on", "Configured");
  const off = t("admin.off", "Not configured");
  const s = sys.data;

  return (
    <div className="space-y-5">
      <PageHeader icon={<Server className="size-5" />} title={t("admin.system", "System")} subtitle={s ? `build ${s.build}` : undefined} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card>
          <CardHeader title={t("admin.runtime", "Runtime")} />
          <CardBody className="py-2">
            {!s ? <Skeleton className="h-64" /> : (
              <>
                <Row label={t("admin.engine", "Trading engine")}><Badge tone={s.engine === "off" ? "down" : "up"}>{s.engine}</Badge></Row>
                <Row label={t("admin.scheduler", "Scheduler")}><Flag on={s.scheduler_running} onLabel={t("admin.running", "Running")} offLabel={t("admin.stopped", "Stopped")} /></Row>
                <Row label={t("admin.market_data", "Market data")}>{s.market_data} · {s.reference_exchange}</Row>
                <Row label={t("admin.database", "Database")}>{s.db_dialect} · {t("admin.tables", "{n} tables", { n: s.tables })}</Row>
                <Row label={t("admin.hosting", "Hosting")}>{s.vercel ? "Vercel (serverless)" : t("admin.server", "Long-running server")}</Row>
                <Row label={t("admin.demo_mode", "Demo mode")}><Flag on={s.demo} onLabel={t("admin.yes", "Yes")} offLabel={t("admin.no", "No")} /></Row>
              </>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("admin.integrations", "Integrations")} />
          <CardBody className="py-2">
            {!s ? <Skeleton className="h-64" /> : (
              <>
                <Row label={t("admin.mail", "Email (SMTP)")}><Flag on={s.mail_configured} onLabel={on} offLabel={off} /></Row>
                <Row label="Stripe"><Flag on={s.stripe_configured} onLabel={on} offLabel={off} /></Row>
                <Row label="Tap"><Flag on={s.tap_configured} onLabel={on} offLabel={off} /></Row>
                <Row label="CRON_SECRET"><Flag on={s.cron_secret} onLabel={on} offLabel={off} /></Row>
                <Row label={t("admin.admin_2fa", "Admin 2FA (TOTP)")}><Flag on={s.admin_totp} onLabel={on} offLabel={off} /></Row>
              </>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("admin.stream", "Real-time stream (ccxt.pro)")} />
          <CardBody className="py-2">
            {!stream.data ? <Skeleton className="h-32" /> : (
              <>
                <Row label={t("admin.status", "Status")}><Flag on={!!stream.data.running} onLabel={t("admin.running", "Running")} offLabel={stream.data.enabled ? t("admin.stopped", "Stopped") : t("admin.disabled", "Disabled (MARKET_STREAM=0)")} /></Row>
                {stream.data.exchange && <Row label={t("admin.exchange", "Exchange")}>{stream.data.exchange}</Row>}
                <Row label={t("admin.symbols", "Symbols")}>{stream.data.symbols.length}</Row>
                <Row label={t("admin.updates", "Ticker updates")}>{stream.data.updates}</Row>
                {stream.data.last_update ? <Row label={t("admin.last_update", "Last update")}>{timeAgo(stream.data.last_update)}</Row> : null}
                {stream.data.last_error ? <Row label={t("admin.error", "Error")}><span className="text-down">{stream.data.last_error}</span></Row> : null}
              </>
            )}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("admin.engine_tick", "Run the engine once")} subtitle={t("admin.engine_tick_sub", "Matches paper orders, fires alerts and steps every active bot / smart trade (20 s budget).")} />
          <CardBody className="space-y-3">
            <Button icon={<Play className="size-4" />} loading={tick.isPending} onClick={() => tick.mutate()}>{t("admin.tick", "Run tick")}</Button>
            {result !== null && <pre className="max-h-64 overflow-auto rounded-xl bg-surface-2 p-3 font-mono text-xs text-fg" dir="ltr">{JSON.stringify(result, null, 2)}</pre>}
          </CardBody>
        </Card>
      </div>
      <div className="flex flex-wrap gap-2">
        {[["/docs/", t("admin.api_docs", "API docs")], ["/api/health", t("admin.health", "Health check")], ["/admin", t("admin.classic", "Classic admin")]].map(([href, label]) => (
          <a key={href} href={href} target={href === "/admin" ? undefined : "_blank"} rel="noreferrer">
            <Button variant="secondary" size="sm" icon={<ExternalLink className="size-4" />}>{label}</Button>
          </a>
        ))}
      </div>
    </div>
  );
}
