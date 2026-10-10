import { useState } from "react";
import { Link } from "react-router";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowDown, ArrowUp, BellPlus, Plus, Star, Trash2 } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v2 } from "../lib/api";
import { useMarketExchange } from "../lib/hooks";
import type { Candle, WatchItem } from "../lib/types";
import { fmtCompact, fmtPrice, symbolToSlug } from "../lib/format";
import { Button, Card, CardBody, EmptyState, IconButton, PageHeader, Skeleton } from "../components/ui";
import { Sparkline } from "../components/charts";
import { Change, Price, SymbolCell, SymbolPicker, useWatchlist } from "../components/market";
import { AlertModal } from "../components/orders";

function Spark({ symbol }: { symbol: string }) {
  const ex = useMarketExchange();
  const q = useQuery({ queryKey: ["spark", ex, symbol], queryFn: () => v2.get<Candle[]>("/market/ohlcv", { exchange: ex, symbol, timeframe: "1h", limit: 48 }), staleTime: 5 * 60_000 });
  return q.data ? <Sparkline values={q.data.map((c) => c[4])} width={110} height={34} /> : <Skeleton className="h-8 w-28" />;
}

export default function Watchlist() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const list = useWatchlist();
  const [pick, setPick] = useState("SOL/USDT");
  const [alertFor, setAlertFor] = useState<WatchItem | null>(null);
  const refresh = () => qc.invalidateQueries({ queryKey: ["watchlist"] });
  const add = useMutation({ mutationFn: () => v2.post("/watchlist", { symbol: pick }), onSuccess: refresh, onError: (e) => toast.error(e) });
  const remove = useMutation({ mutationFn: (id: number) => v2.del(`/watchlist/${id}`), onSuccess: refresh, onError: (e) => toast.error(e) });
  const reorder = useMutation({ mutationFn: (ids: number[]) => v2.put("/watchlist/order", { ids }), onSuccess: refresh });
  const items = list.data ?? [];
  const move = (i: number, d: -1 | 1) => {
    const ids = items.map((x) => x.id);
    const j = i + d;
    if (j < 0 || j >= ids.length) return;
    [ids[i], ids[j]] = [ids[j], ids[i]];
    reorder.mutate(ids);
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<Star className="size-5" />}
        title={t("watch.title", "Watchlist")}
        subtitle={t("watch.subtitle", "Markets you follow, with 48-hour trends.")}
        actions={
          <div className="flex items-center gap-2">
            <SymbolPicker value={pick} onChange={setPick} className="w-44" />
            <Button icon={<Plus className="size-4" />} loading={add.isPending} onClick={() => add.mutate()}>{t("common.add", "Add")}</Button>
          </div>
        }
      />
      {list.isLoading && <Skeleton className="h-64" />}
      {list.data && !items.length && <Card><EmptyState icon={<Star className="size-6" />} title={t("watch.empty", "Your watchlist is empty")} body={t("watch.empty_b", "Tap the ☆ next to any market to follow it.")} /></Card>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {items.map((w, i) => (
          <Card key={w.id}>
            <CardBody className="space-y-3">
              <div className="flex items-start justify-between gap-2">
                <Link to={`/markets/${symbolToSlug(w.symbol)}`}><SymbolCell symbol={w.symbol} /></Link>
                <div className="flex">
                  <IconButton label={t("watch.up", "Move up")} onClick={() => move(i, -1)} disabled={i === 0}><ArrowUp className="size-4" /></IconButton>
                  <IconButton label={t("watch.down", "Move down")} onClick={() => move(i, 1)} disabled={i === items.length - 1}><ArrowDown className="size-4" /></IconButton>
                  <IconButton label={t("alerts.set", "Set alert")} onClick={() => setAlertFor(w)}><BellPlus className="size-4" /></IconButton>
                  <IconButton label={t("watch.remove", "Remove from watchlist")} onClick={() => remove.mutate(w.id)}><Trash2 className="size-4" /></IconButton>
                </div>
              </div>
              <div className="flex items-end justify-between gap-3">
                <div>
                  <p className="text-xl font-semibold"><Price value={w.ticker?.last} className="text-fg" /></p>
                  <Change value={w.ticker?.percentage} arrow className="text-sm" />
                </div>
                <Spark symbol={w.symbol} />
              </div>
              <div className="num flex justify-between text-xs text-muted">
                <span>H {fmtPrice(w.ticker?.high)}</span>
                <span>L {fmtPrice(w.ticker?.low)}</span>
                <span>Vol {fmtCompact(w.ticker?.quoteVolume, "$")}</span>
              </div>
            </CardBody>
          </Card>
        ))}
      </div>
      <AlertModal open={!!alertFor} onClose={() => setAlertFor(null)} symbol={alertFor?.symbol ?? ""} price={alertFor?.ticker?.last} />
    </div>
  );
}
