import { useEffect, useState } from "react";
import { Link } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, LifeBuoy, MessageSquarePlus } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1, v2 } from "../lib/api";
import type { Ticket } from "../lib/types";
import { Button, Card, EmptyState, Field, Input, Modal, Notice, PageHeader, Segmented, Skeleton, Textarea } from "../components/ui";
import { TicketListItem, TicketThread, ticketState } from "../components/support";

function NewTicket({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (t: Ticket) => void }) {
  const t = useT();
  const toast = useToast();
  const [subject, setSubject] = useState("");
  const [content, setContent] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (open) {
      setSubject("");
      setContent("");
    }
  }, [open]);
  const submit = async () => {
    setBusy(true);
    try {
      const ticket = await v1.post<Ticket>("/admin/support/tickets", { subject, content });
      toast.success(t("support.created", "Ticket created — we usually reply within a day."));
      onCreated(ticket);
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={t("support.new", "New ticket")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={busy} disabled={!subject.trim() || !content.trim()} onClick={submit}>{t("support.submit", "Submit ticket")}</Button></>}
    >
      <div className="space-y-4">
        <Field label={t("support.subject", "Subject")}><Input value={subject} maxLength={120} onChange={(e) => setSubject(e.target.value)} placeholder={t("support.subject_ph", "e.g. My bot did not close the deal")} /></Field>
        <Field label={t("support.message", "Message")} hint={t("support.message_hint", "Include the bot or order id and the exchange if it is about a trade.")}>
          <Textarea rows={6} value={content} onChange={(e) => setContent(e.target.value)} />
        </Field>
      </div>
    </Modal>
  );
}

export default function Support() {
  const t = useT();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"all" | "open" | "closed">("all");
  const [selected, setSelected] = useState<number | null>(null);
  const [creating, setCreating] = useState(false);
  const list = useQuery({ queryKey: ["tickets"], queryFn: () => v2.get<Ticket[]>("/support/tickets"), refetchInterval: 30_000 });
  const tickets = (list.data ?? []).filter((x) => filter === "all" || (filter === "closed" ? x.status === "closed" : x.status !== "closed"));
  const current = list.data?.find((x) => x.id === selected) ?? null;
  const refresh = () => qc.invalidateQueries({ queryKey: ["tickets"] });
  const answered = (list.data ?? []).filter((x) => ticketState(x) === "answered").length;

  useEffect(() => {
    if (selected === null && list.data?.length) setSelected(list.data[0].id);
  }, [list.data, selected]);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<LifeBuoy className="size-5" />}
        title={t("nav.support", "Support")}
        subtitle={t("support.subtitle", "Talk to the PulseTrade team. Replies also arrive as notifications.")}
        actions={
          <>
            <Link to="/kb"><Button variant="secondary" size="sm" icon={<BookOpen className="size-4" />}>{t("nav.kb", "Knowledge base")}</Button></Link>
            <Button icon={<MessageSquarePlus className="size-4" />} onClick={() => setCreating(true)}>{t("support.new", "New ticket")}</Button>
          </>
        }
      />
      {answered > 0 && <Notice tone="success">{t("support.has_answers", "{n} ticket(s) have a new reply from support.", { n: answered })}</Notice>}
      {list.isLoading ? <Skeleton className="h-96" /> : !list.data?.length ? (
        <Card>
          <EmptyState
            icon={<LifeBuoy className="size-6" />}
            title={t("support.empty", "No tickets yet")}
            body={t("support.empty_b", "Questions about bots, exchanges or billing? Open a ticket and we'll help.")}
            action={<Button onClick={() => setCreating(true)}>{t("support.new", "New ticket")}</Button>}
          />
        </Card>
      ) : (
        <div className="grid gap-5 lg:grid-cols-[320px_minmax(0,1fr)]">
          <Card className="self-start overflow-hidden">
            <div className="border-b border-line p-3">
              <Segmented size="xs" value={filter} onChange={setFilter} className="w-full" options={[
                { value: "all", label: t("common.all", "All") },
                { value: "open", label: t("support.open", "Open") },
                { value: "closed", label: t("support.closed", "Closed") },
              ]} />
            </div>
            <div className="max-h-[65vh] overflow-y-auto">
              {tickets.map((x) => <TicketListItem key={x.id} ticket={x} active={x.id === selected} onClick={() => setSelected(x.id)} />)}
              {!tickets.length && <p className="p-4 text-center text-sm text-muted">{t("support.none_filter", "Nothing here.")}</p>}
            </div>
          </Card>
          <Card className="overflow-hidden">
            {current ? <TicketThread ticket={current} onChanged={refresh} /> : <EmptyState title={t("support.pick", "Select a ticket")} />}
          </Card>
        </div>
      )}
      <NewTicket
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(ticket) => {
          setCreating(false);
          setSelected(ticket.id);
          refresh();
        }}
      />
    </div>
  );
}
