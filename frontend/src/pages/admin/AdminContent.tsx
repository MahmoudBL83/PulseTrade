import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { BookOpen, Eye, FolderPlus, LifeBuoy, Megaphone, Pencil, Plus, Search, Send, Trash2 } from "lucide-react";
import { useToast } from "../../context/toast";
import { useT } from "../../i18n";
import { v1, v2 } from "../../lib/api";
import type { KbCategory, KbPost, Ticket } from "../../lib/types";
import { fmtDate } from "../../lib/format";
import { sanitizeHtml } from "../../lib/utils";
import { Badge, Button, Card, CardBody, CardHeader, ConfirmButton, EmptyState, Field, IconButton, Input, Modal, Notice, PageHeader, Segmented, Select, Skeleton, Table, Tabs, Td, Textarea, Th } from "../../components/ui";
import { TicketListItem, TicketThread, ticketState } from "../../components/support";

/* ------------------------------------------------------------------ support desk */

export function AdminSupport() {
  const t = useT();
  const qc = useQueryClient();
  const [filter, setFilter] = useState<"waiting" | "open" | "closed" | "all">("waiting");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<number | null>(null);
  const list = useQuery({ queryKey: ["admin", "tickets"], queryFn: () => v1.get<Ticket[]>("/admin/support/tickets"), refetchInterval: 30_000 });
  const all = list.data ?? [];
  const counts = {
    waiting: all.filter((x) => ticketState(x) === "open").length,
    open: all.filter((x) => x.status !== "closed").length,
    closed: all.filter((x) => x.status === "closed").length,
    all: all.length,
  };
  const needle = q.trim().toLowerCase();
  const rows = all.filter((x) => {
    const s = ticketState(x);
    const pass = filter === "all" || (filter === "waiting" ? s === "open" : filter === "closed" ? s === "closed" : s !== "closed");
    return pass && (!needle || x.subject.toLowerCase().includes(needle) || (x.user?.email ?? "").toLowerCase().includes(needle) || String(x.id) === needle);
  });
  const current = all.find((x) => x.id === selected) ?? null;
  useEffect(() => {
    if (!current && rows.length) setSelected(rows[0].id);
  }, [rows, current]);
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin", "tickets"] });

  return (
    <div className="space-y-5">
      <PageHeader icon={<LifeBuoy className="size-5" />} title={t("admin.support", "Support desk")} subtitle={t("admin.support_sub", "{n} ticket(s) waiting for a reply.", { n: counts.waiting })} />
      {list.isLoading ? <Skeleton className="h-96" /> : (
        <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
          <Card className="self-start overflow-hidden">
            <div className="space-y-2 border-b border-line p-3">
              <Tabs
                value={filter}
                onChange={setFilter}
                className="border-0"
                tabs={[
                  { value: "waiting", label: t("support.needs_reply", "Needs reply"), count: counts.waiting },
                  { value: "open", label: t("support.open", "Open"), count: counts.open },
                  { value: "closed", label: t("support.closed", "Closed"), count: counts.closed },
                  { value: "all", label: t("common.all", "All"), count: counts.all },
                ]}
              />
              <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("admin.search_tickets", "Subject, email or #id…")} prefix={<Search className="size-4" />} />
            </div>
            <div className="max-h-[65vh] overflow-y-auto">
              {rows.map((x) => <TicketListItem key={x.id} ticket={x} admin active={x.id === selected} onClick={() => setSelected(x.id)} />)}
              {!rows.length && <p className="p-6 text-center text-sm text-muted">{t("admin.inbox_zero", "Inbox zero 🎉")}</p>}
            </div>
          </Card>
          <Card className="overflow-hidden">
            {current ? <TicketThread ticket={current} admin onChanged={refresh} /> : <EmptyState icon={<LifeBuoy className="size-6" />} title={t("support.pick", "Select a ticket")} />}
          </Card>
        </div>
      )}
    </div>
  );
}

/* ------------------------------------------------------------------ knowledge base */

function CategoryModal({ open, cat, onClose }: { open: boolean; cat: KbCategory | null; onClose: () => void }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [f, setF] = useState({ title: "", title_ar: "", img: "" });
  useEffect(() => {
    if (open) setF({ title: cat?.title ?? "", title_ar: cat?.title_ar ?? "", img: cat?.img ?? "" });
  }, [open, cat]);
  const save = useMutation({
    mutationFn: () => v1.post(cat ? `/admin/blog/cats/edit/${cat.id}` : "/admin/blog/cats", { ...f, img: f.img || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb"] });
      toast.success(t("admin.saved", "Saved"));
      onClose();
    },
    onError: (e) => toast.error(e),
  });
  return (
    <Modal
      open={open}
      onClose={onClose}
      title={cat ? t("admin.edit_cat", "Edit category") : t("admin.new_cat", "New category")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={save.isPending} disabled={!f.title.trim()} onClick={() => save.mutate()}>{t("common.save", "Save")}</Button></>}
    >
      <div className="space-y-4">
        <Field label={t("admin.name_en", "Name (English)")}><Input value={f.title} maxLength={120} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
        <Field label={t("admin.name_ar", "Name (Arabic)")}><Input dir="rtl" value={f.title_ar} maxLength={120} onChange={(e) => setF({ ...f, title_ar: e.target.value })} /></Field>
        <Field label={t("admin.image", "Image URL")}><Input value={f.img} onChange={(e) => setF({ ...f, img: e.target.value })} placeholder="https://…" /></Field>
      </div>
    </Modal>
  );
}

type FullPost = KbPost & { content: string };

function PostModal({ open, post, cats, onClose }: { open: boolean; post: FullPost | null; cats: KbCategory[]; onClose: () => void }) {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [view, setView] = useState<"edit" | "preview">("edit");
  const [f, setF] = useState({ title: "", category_id: "", lang: "en", writer: "PulseTrade", img: "", content: "" });
  useEffect(() => {
    if (!open) return;
    setView("edit");
    setF(post
      ? { title: post.title, category_id: String(post.category_id ?? ""), lang: post.lang || "en", writer: post.writer, img: post.img ?? "", content: post.content ?? "" }
      : { title: "", category_id: String(cats[0]?.id ?? ""), lang: "en", writer: "PulseTrade", img: "", content: "" });
  }, [open, post, cats]);
  const preview = useMemo(() => (view === "preview" ? sanitizeHtml(f.content) : ""), [view, f.content]);
  const save = useMutation({
    mutationFn: () => {
      const body = { ...f, category_id: f.category_id ? Number(f.category_id) : null, img: f.img || null };
      return post ? v1.put(`/admin/blog/posts/${post.id}`, body) : v1.post("/admin/blog/posts", body);
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["kb"] });
      qc.invalidateQueries({ queryKey: ["admin", "posts"] });
      toast.success(post ? t("admin.post_updated", "Article updated") : t("admin.post_published", "Article published"));
      onClose();
    },
    onError: (e) => toast.error(e),
  });
  return (
    <Modal
      open={open}
      onClose={onClose}
      size="xl"
      title={post ? t("admin.edit_post", "Edit article") : t("admin.new_post", "New article")}
      footer={<><Button variant="secondary" onClick={onClose}>{t("common.cancel", "Cancel")}</Button><Button loading={save.isPending} disabled={!f.title.trim() || !f.content.trim() || !f.category_id} onClick={() => save.mutate()}>{post ? t("common.save", "Save") : t("admin.publish", "Publish")}</Button></>}
    >
      <div className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label={t("journal.title", "Title")} className="sm:col-span-2"><Input value={f.title} maxLength={120} dir={f.lang === "ar" ? "rtl" : undefined} onChange={(e) => setF({ ...f, title: e.target.value })} /></Field>
          <Field label={t("admin.category", "Category")}>
            <Select value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })}>
              {!cats.length && <option value="">{t("admin.create_cat_first", "Create a category first")}</option>}
              {cats.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
            </Select>
          </Field>
          <Field label={t("settings.language", "Language")}>
            <Select value={f.lang} onChange={(e) => setF({ ...f, lang: e.target.value })}>
              <option value="en">English</option>
              <option value="ar">العربية</option>
            </Select>
          </Field>
          <Field label={t("admin.writer", "Author")}><Input value={f.writer} maxLength={120} onChange={(e) => setF({ ...f, writer: e.target.value })} /></Field>
          <Field label={t("admin.cover", "Cover image URL")}><Input value={f.img} onChange={(e) => setF({ ...f, img: e.target.value })} placeholder="https://…" /></Field>
        </div>
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-muted">{t("admin.content_html", "Content (HTML)")}</span>
          <Segmented size="xs" value={view} onChange={setView} options={[{ value: "edit", label: t("common.edit", "Edit") }, { value: "preview", label: t("admin.preview", "Preview") }]} />
        </div>
        {view === "edit" ? (
          <Textarea rows={16} className="font-mono text-xs" dir="ltr" value={f.content} onChange={(e) => setF({ ...f, content: e.target.value })} placeholder="<h2>…</h2><p>…</p>" />
        ) : (
          <div className="max-h-[50vh] overflow-y-auto rounded-xl border border-line p-5">
            <div className="prose-pt" dir={f.lang === "ar" ? "rtl" : "ltr"} dangerouslySetInnerHTML={{ __html: preview }} />
          </div>
        )}
        <p className="text-xs text-muted">{t("admin.html_note", "Scripts, iframes, inline styles and event handlers are stripped when the article is displayed.")}</p>
      </div>
    </Modal>
  );
}

export function AdminKb() {
  const t = useT();
  const toast = useToast();
  const qc = useQueryClient();
  const [catModal, setCatModal] = useState<{ open: boolean; cat: KbCategory | null }>({ open: false, cat: null });
  const [postModal, setPostModal] = useState<{ open: boolean; post: FullPost | null }>({ open: false, post: null });
  const [q, setQ] = useState("");
  const cats = useQuery({ queryKey: ["kb", "cats"], queryFn: () => v2.get<KbCategory[]>("/kb/categories") });
  const posts = useQuery({ queryKey: ["admin", "posts"], queryFn: () => v1.get<FullPost[]>("/admin/blog/posts") });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["kb"] });
    qc.invalidateQueries({ queryKey: ["admin", "posts"] });
  };
  const delCat = (id: number) => v1.del(`/admin/blog/cats/${id}`).then(refresh).catch((e) => toast.error(e));
  const delPost = (id: number) => v1.del(`/admin/blog/posts/${id}`).then(refresh).catch((e) => toast.error(e));
  const catName = new Map((cats.data ?? []).map((c) => [c.id, c.title]));
  const needle = q.trim().toLowerCase();
  const rows = (posts.data ?? []).filter((p) => !needle || p.title.toLowerCase().includes(needle)).sort((a, b) => b.id - a.id);

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<BookOpen className="size-5" />}
        title={t("admin.kb", "Knowledge base")}
        subtitle={t("admin.kb_sub", "Articles appear in the app and on the classic knowledge-base pages.")}
        actions={
          <>
            <Button variant="secondary" size="sm" icon={<FolderPlus className="size-4" />} onClick={() => setCatModal({ open: true, cat: null })}>{t("admin.new_cat", "New category")}</Button>
            <Button icon={<Plus className="size-4" />} onClick={() => setPostModal({ open: true, post: null })}>{t("admin.new_post", "New article")}</Button>
          </>
        }
      />
      <div className="grid gap-5 xl:grid-cols-[320px_minmax(0,1fr)]">
        <Card className="self-start">
          <CardHeader title={t("admin.categories", "Categories")} />
          <CardBody className="space-y-1 p-2 sm:p-2">
            {cats.isLoading && <Skeleton className="h-32" />}
            {cats.data?.map((c) => (
              <div key={c.id} className="flex items-center justify-between gap-2 rounded-lg px-3 py-2 hover:bg-surface-2">
                <div className="min-w-0">
                  <p className="truncate text-sm font-medium text-fg">{c.title}</p>
                  <p className="truncate text-xs text-muted">{c.title_ar || "—"} · {t("admin.n_posts", "{n} articles", { n: c.post_count })}</p>
                </div>
                <div className="flex shrink-0">
                  <IconButton label={t("common.edit", "Edit")} onClick={() => setCatModal({ open: true, cat: c })}><Pencil className="size-4" /></IconButton>
                  <ConfirmButton title={t("admin.del_cat_q", "Delete “{name}”?", { name: c.title })} body={t("admin.del_cat_b", "All {n} articles in this category are deleted too.", { n: c.post_count })} confirmLabel={t("common.delete", "Delete")} onConfirm={() => delCat(c.id)}>
                    <Trash2 className="size-4" />
                  </ConfirmButton>
                </div>
              </div>
            ))}
            {cats.data && !cats.data.length && <p className="p-3 text-sm text-muted">{t("admin.no_cats", "No categories yet.")}</p>}
          </CardBody>
        </Card>
        <Card>
          <CardHeader title={t("admin.articles", "Articles")} actions={<Input className="w-56" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("admin.filter", "Filter…")} prefix={<Search className="size-4" />} />} />
          {posts.isLoading ? <Skeleton className="m-4 h-40" /> : !rows.length ? <EmptyState icon={<BookOpen className="size-6" />} title={t("kb.empty", "No articles found")} /> : (
            <Table>
              <thead><tr><Th>{t("journal.title", "Title")}</Th><Th>{t("admin.category", "Category")}</Th><Th>{t("settings.language", "Language")}</Th><Th align="end">{t("admin.views", "Views")}</Th><Th>{t("admin.published", "Published")}</Th><Th align="end" /></tr></thead>
              <tbody>
                {rows.map((p) => (
                  <tr key={p.id}>
                    <Td className="max-w-80 truncate font-medium text-fg">{p.title}</Td>
                    <Td className="text-muted">{p.category_id ? catName.get(p.category_id) ?? "—" : "—"}</Td>
                    <Td><Badge>{p.lang === "ar" ? "AR" : "EN"}</Badge></Td>
                    <Td align="end" className="num">{p.views}</Td>
                    <Td className="text-muted">{fmtDate(p.created_at)}</Td>
                    <Td align="end">
                      <a href={`/app/kb/${p.id}`} target="_blank" rel="noreferrer" aria-label={t("admin.preview", "Preview")} title={t("admin.preview", "Preview")} className="inline-flex size-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-fg"><Eye className="size-4" /></a>
                      <IconButton label={t("common.edit", "Edit")} onClick={() => setPostModal({ open: true, post: p })}><Pencil className="size-4" /></IconButton>
                      <ConfirmButton title={t("admin.del_post_q", "Delete this article?")} confirmLabel={t("common.delete", "Delete")} onConfirm={() => delPost(p.id)}><Trash2 className="size-4" /></ConfirmButton>
                    </Td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Card>
      </div>
      <CategoryModal open={catModal.open} cat={catModal.cat} onClose={() => setCatModal({ open: false, cat: null })} />
      <PostModal open={postModal.open} post={postModal.post} cats={cats.data ?? []} onClose={() => setPostModal({ open: false, post: null })} />
    </div>
  );
}

/* ------------------------------------------------------------------ broadcast */

export function AdminBroadcast() {
  const t = useT();
  const toast = useToast();
  const [message, setMessage] = useState("");
  const send = async () => {
    try {
      await v1.post("/api/admin/v1/send_custom_notification_all", { message: message.trim() });
      toast.success(t("admin.broadcast_ok", "Broadcast sent to every user"));
      setMessage("");
    } catch (e) {
      toast.error(e);
    }
  };
  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <PageHeader icon={<Megaphone className="size-5" />} title={t("admin.broadcast", "Broadcast")} subtitle={t("admin.broadcast_sub", "Send an in-app notification to every user (also forwarded to their enabled channels).")} />
      <Card>
        <CardBody className="space-y-4">
          <Field label={t("support.message", "Message")}>
            <Textarea rows={6} value={message} maxLength={1000} onChange={(e) => setMessage(e.target.value)} placeholder={t("admin.broadcast_ph", "e.g. Scheduled maintenance on Sunday 02:00–02:30 UTC.")} />
          </Field>
          <Notice tone="warning">{t("admin.broadcast_warn", "This cannot be undone. Keep it short — it appears in every user's notification bell.")}</Notice>
          <div className="flex justify-end">
            <ConfirmButton variant="primary" size="md" disabled={!message.trim()} title={t("admin.broadcast_q", "Send to every user?")} body={message} confirmLabel={t("support.send", "Send")} onConfirm={send}>
              <Send className="size-4" />{t("admin.send_all", "Send to all users")}
            </ConfirmButton>
          </div>
        </CardBody>
      </Card>
    </div>
  );
}
