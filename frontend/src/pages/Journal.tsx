import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, NotebookPen, Pencil, Plus, Search, Trash2 } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { download, v2 } from "../lib/api";
import type { JournalEntry } from "../lib/types";
import { fmtDateTime, fmtPct, fmtPrice, fmtUsd, trendClass } from "../lib/format";
import { cn, toNumber, useDebounced } from "../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, ConfirmButton, EmptyState, Field, IconButton, Input, Modal, PageHeader, Segmented, Select, Skeleton, Stat, Textarea } from "../components/ui";

interface JStats { entries: number; closed: number; pnl: number; win_rate: number; avg_win: number; avg_loss: number; by_tag: { tag: string; trades: number; pnl: number }[] }

const MOODS = ["😌 calm", "😃 confident", "😬 anxious", "😤 FOMO", "😴 bored"];

function EntryModal({ open, onClose, entry }: { open: boolean; onClose: () => void; entry: JournalEntry | null }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const blank = { title: "", body: "", symbol: "", side: "long", entry_price: "", exit_price: "", amount: "", tags: "", mood: "" };
  const [f, setF] = useState(blank);
  useEffect(() => {
    if (!open) return;
    setF(entry ? {
      title: entry.title, body: entry.body ?? "", symbol: entry.symbol ?? "", side: entry.side ?? "long",
      entry_price: entry.entry_price?.toString() ?? "", exit_price: entry.exit_price?.toString() ?? "",
      amount: entry.amount?.toString() ?? "", tags: (entry.tags ?? []).join(", "), mood: entry.mood ?? "",
    } : blank);
  }, [open, entry]); // eslint-disable-line react-hooks/exhaustive-deps
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, entry_price: f.entry_price || null, exit_price: f.exit_price || null, amount: f.amount || null, symbol: f.symbol || null, mood: f.mood || null };
      return entry ? v2.put(`/journal/${entry.id}`, body) : v2.post("/journal", body);
    },
    onSuccess: () => {
      toast.success(t("journal.saved", "Entry saved"));
      qc.invalidateQueries({ queryKey: ["journal"] });
      onClose();
    },
    onError: (e) => toast.error(e),
  });
  const pnl = toNumber(f.entry_price) && toNumber(f.exit_price) && toNumber(f.amount)
    ? (f.side === "short" ? -1 : 1) * (toNumber(f.exit_price) - toNumber(f.entry_price)) * toNumber(f.amount) : null;
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="lg"
      title={entry ? t("journal.edit", "Edit entry") : t("journal.new", "New journal entry")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={save.isPending} disabled={!f.title.trim()} onClick={() => save.mutate()}>{t("common.save", "Save")}</Button></>}
    >
      <div className="space-y-4">
        <Field label={t("journal.title", "Title")}><Input value={f.title} maxLength={160} onChange={(e) => setF({ ...f, title: e.target.value })} placeholder={t("journal.title_ph", "e.g. BTC breakout retest")} /></Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label={t("market.pair", "Pair")}><Input value={f.symbol} onChange={(e) => setF({ ...f, symbol: e.target.value.toUpperCase() })} placeholder="BTC/USDT" /></Field>
          <Field label={t("order.side", "Side")}><Segmented value={f.side} onChange={(v) => setF({ ...f, side: v })} className="w-full" options={[{ value: "long", label: t("bots.long", "Long"), tone: "up" }, { value: "short", label: t("bots.short", "Short"), tone: "down" }]} /></Field>
          <Field label={t("journal.mood", "Mood")}>
            <Select value={f.mood} onChange={(e) => setF({ ...f, mood: e.target.value })}>
              <option value="">—</option>
              {MOODS.map((m) => <option key={m} value={m}>{m}</option>)}
            </Select>
          </Field>
          <Field label={t("bt.entry", "Entry")}><Input inputMode="decimal" value={f.entry_price} onChange={(e) => setF({ ...f, entry_price: e.target.value })} /></Field>
          <Field label={t("bt.exit", "Exit")}><Input inputMode="decimal" value={f.exit_price} onChange={(e) => setF({ ...f, exit_price: e.target.value })} /></Field>
          <Field label={t("order.amount", "Amount")}><Input inputMode="decimal" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} /></Field>
        </div>
        {pnl !== null && <p className={cn("num text-sm", trendClass(pnl))}>P&L {fmtUsd(pnl)}</p>}
        <Field label={t("journal.tags", "Tags")} hint={t("journal.tags_hint", "Comma separated, e.g. breakout, news")}><Input value={f.tags} onChange={(e) => setF({ ...f, tags: e.target.value })} /></Field>
        <Field label={t("journal.notes", "Notes")}><Textarea rows={6} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} placeholder={t("journal.notes_ph", "Why did you take the trade? What did you learn?")} /></Field>
      </div>
    </Modal>
  );
}

export default function Journal() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [tag, setTag] = useState("");
  const dq = useDebounced(q, 300);
  const [modal, setModal] = useState<{ open: boolean; entry: JournalEntry | null }>({ open: false, entry: null });
  const list = useQuery({ queryKey: ["journal", dq, tag], queryFn: () => v2.get<JournalEntry[]>("/journal", { q: dq, tag }) });
  const stats = useQuery({ queryKey: ["journal", "stats"], queryFn: () => v2.get<JStats>("/journal/stats") });
  const del = useMutation({
    mutationFn: (id: number) => v2.del(`/journal/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["journal"] }),
    onError: (e) => toast.error(e),
  });
  const s = stats.data;

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<NotebookPen className="size-5" />}
        title={t("nav.journal", "Journal")}
        subtitle={t("journal.subtitle", "Record your reasoning and review what actually works.")}
        actions={
          <>
            <Button variant="secondary" size="sm" icon={<Download className="size-4" />} onClick={() => download("/api/v2/export/journal.csv", "pulsetrade-journal.csv").catch((e) => toast.error(e))}>{t("history.export", "Export CSV")}</Button>
            <Button icon={<Plus className="size-4" />} onClick={() => setModal({ open: true, entry: null })}>{t("journal.new", "New journal entry")}</Button>
          </>
        }
      />
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Card className="p-4"><Stat label={t("journal.entries", "Entries")} value={s?.entries ?? "—"} hint={t("journal.closed_n", "{n} with a result", { n: s?.closed ?? 0 })} /></Card>
        <Card className="p-4"><Stat label={t("journal.total_pnl", "Total P&L")} value={fmtUsd(s?.pnl ?? 0)} tone={trendClass(s?.pnl)} /></Card>
        <Card className="p-4"><Stat label={t("bt.winrate", "Win rate")} value={fmtPct(s?.win_rate ?? 0, 1, false)} /></Card>
        <Card className="p-4"><Stat label={t("journal.avg", "Avg win / loss")} value={`${fmtUsd(s?.avg_win ?? 0)} / ${fmtUsd(s?.avg_loss ?? 0)}`} /></Card>
      </div>
      <div className="grid gap-5 xl:grid-cols-[1fr_300px]">
        <div className="space-y-3">
          <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("journal.search", "Search entries…")} prefix={<Search className="size-4" />} />
          {tag && <Badge tone="primary" className="py-1">#{tag} <button type="button" onClick={() => setTag("")}>✕</button></Badge>}
          {list.isLoading && <Skeleton className="h-40" />}
          {list.data && !list.data.length && <Card><EmptyState icon={<NotebookPen className="size-6" />} title={t("journal.empty", "No entries yet")} body={t("journal.empty_b", "Journaling your trades is the fastest way to improve.")} /></Card>}
          {list.data?.map((e) => (
            <Card key={e.id}>
              <CardBody className="space-y-2">
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0">
                    <h3 className="font-semibold text-fg">{e.title}</h3>
                    <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">
                      <span>{fmtDateTime(e.created_at)}</span>
                      {e.symbol && <Badge>{e.symbol}</Badge>}
                      {e.side && <Badge tone={e.side === "short" ? "down" : "up"}>{e.side}</Badge>}
                      {e.mood && <span>{e.mood}</span>}
                    </p>
                  </div>
                  <div className="flex items-center gap-1">
                    {e.pnl !== null && <span className={cn("num me-2 text-sm font-semibold", trendClass(e.pnl))}>{fmtUsd(e.pnl)}</span>}
                    <IconButton label={t("common.edit", "Edit")} onClick={() => setModal({ open: true, entry: e })}><Pencil className="size-4" /></IconButton>
                    <ConfirmButton title={t("journal.delete_q", "Delete this entry?")} confirmLabel={t("common.delete", "Delete")} onConfirm={() => del.mutateAsync(e.id)}><Trash2 className="size-4" /></ConfirmButton>
                  </div>
                </div>
                {(e.entry_price || e.exit_price) && <p className="num text-xs text-muted">{fmtPrice(e.entry_price)} → {fmtPrice(e.exit_price)} × {e.amount ?? "—"}</p>}
                {e.body && <p className="text-sm whitespace-pre-wrap text-fg/90">{e.body}</p>}
                {!!e.tags.length && <div className="flex flex-wrap gap-1.5">{e.tags.map((x) => <button key={x} type="button" onClick={() => setTag(x)}><Badge tone="info">#{x}</Badge></button>)}</div>}
              </CardBody>
            </Card>
          ))}
        </div>
        <Card className="self-start">
          <CardHeader title={t("journal.by_tag", "P&L by tag")} />
          <CardBody className="space-y-2">
            {!s?.by_tag.length && <p className="text-sm text-muted">{t("journal.no_tags", "Tag closed trades to compare setups.")}</p>}
            {s?.by_tag.map((r) => (
              <button key={r.tag} type="button" onClick={() => setTag(r.tag)} className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-sm hover:bg-surface-2">
                <span className="text-fg">#{r.tag} <span className="text-xs text-muted">({r.trades})</span></span>
                <span className={cn("num", trendClass(r.pnl))}>{fmtUsd(r.pnl)}</span>
              </button>
            ))}
          </CardBody>
        </Card>
      </div>
      <EntryModal open={modal.open} entry={modal.entry} onClose={() => setModal({ open: false, entry: null })} />
    </div>
  );
}
