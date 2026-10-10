import { useEffect, useRef, useState } from "react";
import { CheckCircle2, Headset, Lock, Send } from "lucide-react";
import { useToast } from "../context/toast";
import { useT } from "../i18n";
import { v1 } from "../lib/api";
import type { Ticket } from "../lib/types";
import { fmtDateTime, timeAgo } from "../lib/format";
import { cn } from "../lib/utils";
import { Badge, Button, ConfirmButton, Textarea } from "./ui";

/** open · waiting (support replied, user's turn) · closed */
export function ticketState(t: Ticket): "open" | "answered" | "closed" {
  if (t.status === "closed") return "closed";
  const last = t.messages[t.messages.length - 1];
  return last?.is_admin ? "answered" : "open";
}

export function TicketStatus({ ticket, admin }: { ticket: Ticket; admin?: boolean }) {
  const t = useT();
  const s = ticketState(ticket);
  if (s === "closed") return <Badge>{t("support.closed", "Closed")}</Badge>;
  if (s === "answered") return <Badge tone="up">{admin ? t("support.replied", "Replied") : t("support.answered", "Answered")}</Badge>;
  return <Badge tone="primary">{admin ? t("support.needs_reply", "Needs reply") : t("support.open", "Open")}</Badge>;
}

export function TicketListItem({ ticket, active, onClick, admin }: { ticket: Ticket; active: boolean; onClick: () => void; admin?: boolean }) {
  const last = ticket.messages[ticket.messages.length - 1];
  return (
    <button
      type="button"
      onClick={onClick}
      className={cn("w-full border-b border-line/60 px-4 py-3 text-start transition-colors last:border-0", active ? "bg-primary-soft/50" : "hover:bg-surface-2")}
    >
      <div className="flex items-center justify-between gap-2">
        <p className="truncate text-sm font-medium text-fg">{ticket.subject}</p>
        <TicketStatus ticket={ticket} admin={admin} />
      </div>
      {admin && ticket.user && <p className="mt-0.5 truncate text-xs text-muted">{ticket.user.email}</p>}
      {last && <p className="mt-1 truncate text-xs text-muted">{last.content}</p>}
      <p className="mt-1 text-[11px] text-muted">#{ticket.id} · {timeAgo(ticket.updated_at ?? ticket.created_at)}</p>
    </button>
  );
}

export function TicketThread({ ticket, admin, onChanged }: { ticket: Ticket; admin?: boolean; onChanged: () => void }) {
  const t = useT();
  const toast = useToast();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const end = useRef<HTMLDivElement>(null);
  useEffect(() => end.current?.scrollIntoView({ block: "end" }), [ticket.id, ticket.messages.length]);

  const send = async () => {
    const content = text.trim();
    if (!content) return;
    setBusy(true);
    try {
      await v1.post(`/admin/support/tickets/${ticket.id}/messages`, admin ? { content, is_admin: true } : { content });
      setText("");
      onChanged();
    } catch (e) {
      toast.error(e);
    } finally {
      setBusy(false);
    }
  };
  const close = async () => {
    try {
      await v1.put(`/admin/support/tickets/${ticket.id}/close`);
      toast.success(t("support.closed_ok", "Ticket closed"));
      onChanged();
    } catch (e) {
      toast.error(e);
    }
  };
  const closed = ticket.status === "closed";

  return (
    <div className="flex h-full min-h-[420px] flex-col">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-line px-5 py-3">
        <div className="min-w-0">
          <h2 className="truncate font-semibold text-fg">{ticket.subject}</h2>
          <p className="mt-0.5 text-xs text-muted">
            #{ticket.id} · {fmtDateTime(ticket.created_at)}
            {admin && ticket.user && <> · {ticket.user.email}</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <TicketStatus ticket={ticket} admin={admin} />
          {!closed && (
            <ConfirmButton title={t("support.close_q", "Close this ticket?")} body={t("support.close_b", "You can reopen it by sending a new message.")} confirmLabel={t("support.close", "Close ticket")} variant="secondary" onConfirm={close}>
              <Lock className="size-3.5" />{t("support.close", "Close ticket")}
            </ConfirmButton>
          )}
        </div>
      </div>
      <div className="flex-1 space-y-3 overflow-y-auto px-5 py-4" style={{ maxHeight: "60vh" }}>
        {ticket.messages.map((m) => {
          const mine = admin ? m.is_admin : !m.is_admin;
          return (
            <div key={m.id} className={cn("flex", mine ? "justify-end" : "justify-start")}>
              <div className={cn("max-w-[85%] rounded-2xl px-4 py-2.5 text-sm", mine ? "rounded-ee-sm bg-primary text-primary-fg" : "rounded-es-sm bg-surface-2 text-fg")}>
                {m.is_admin && !mine && (
                  <p className="mb-1 flex items-center gap-1 text-xs font-semibold text-primary"><Headset className="size-3.5" />{t("support.team", "PulseTrade support")}</p>
                )}
                <p className="whitespace-pre-wrap">{m.content}</p>
                <p className={cn("mt-1 text-[10px]", mine ? "text-primary-fg/70" : "text-muted")}>{fmtDateTime(m.created_at)}</p>
              </div>
            </div>
          );
        })}
        {closed && (
          <p className="flex items-center justify-center gap-1.5 py-2 text-xs text-muted"><CheckCircle2 className="size-3.5" />{t("support.closed_note", "This ticket is closed. Replying reopens it.")}</p>
        )}
        <div ref={end} />
      </div>
      <div className="border-t border-line p-3">
        <div className="flex items-end gap-2">
          <Textarea
            rows={2}
            className="min-h-0 flex-1 resize-none"
            value={text}
            placeholder={t("support.reply_ph", "Write a reply… (Ctrl+Enter to send)")}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
                e.preventDefault();
                send();
              }
            }}
          />
          <Button icon={<Send className="size-4" />} loading={busy} disabled={!text.trim()} onClick={send}>
            {t("support.send", "Send")}
          </Button>
        </div>
      </div>
    </div>
  );
}
