import { useState } from "react";
import { Link, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { BookOpen, Eye, LifeBuoy, Search } from "lucide-react";
import { useAuth } from "../context/auth";
import { useI18n, useT } from "../i18n";
import { v2 } from "../lib/api";
import type { KbCategory, KbPost } from "../lib/types";
import { fmtDate } from "../lib/format";
import { cn, useDebounced } from "../lib/utils";
import { Button, Card, EmptyState, Input, PageHeader, Segmented, Skeleton } from "../components/ui";

export function PostCard({ post, category }: { post: KbPost; category?: KbCategory }) {
  const { lang } = useI18n();
  return (
    <Link to={`/kb/${post.id}`} className="group block">
      <Card className="flex h-full flex-col overflow-hidden transition-colors group-hover:border-primary/60">
        {post.img ? (
          <img src={post.img} alt="" loading="lazy" className="aspect-[16/8] w-full object-cover" />
        ) : (
          <div className="flex aspect-[16/8] w-full items-center justify-center bg-gradient-to-br from-primary-soft to-surface-2">
            <BookOpen className="size-8 text-primary/70" />
          </div>
        )}
        <div className="flex flex-1 flex-col p-4" dir={post.lang === "ar" ? "rtl" : undefined}>
          {category && <p className="text-xs font-medium text-primary">{(lang === "ar" && category.title_ar) || category.title}</p>}
          <h3 className="mt-1 line-clamp-2 font-semibold text-fg group-hover:text-primary">{post.title}</h3>
          {post.excerpt && <p className="mt-2 line-clamp-3 flex-1 text-sm text-muted">{post.excerpt}</p>}
          <p className="mt-3 flex items-center gap-2 text-xs text-muted">
            <span>{post.writer}</span>·<span>{fmtDate(post.created_at)}</span>·<span className="inline-flex items-center gap-1"><Eye className="size-3" />{post.views}</span>
          </p>
        </div>
      </Card>
    </Link>
  );
}

export default function KnowledgeBase() {
  const t = useT();
  const { lang: uiLang } = useI18n();
  const { user } = useAuth();
  const [params, setParams] = useSearchParams();
  const category = params.get("category") ?? "";
  const [q, setQ] = useState(params.get("q") ?? "");
  const [lang, setLang] = useState<"all" | "en" | "ar">("all");
  const dq = useDebounced(q, 300);
  const cats = useQuery({ queryKey: ["kb", "cats"], queryFn: () => v2.get<KbCategory[]>("/kb/categories"), staleTime: 5 * 60_000 });
  const posts = useQuery({
    queryKey: ["kb", "posts", category, dq, lang],
    queryFn: () => v2.get<KbPost[]>("/kb/posts", { category, q: dq, lang: lang === "all" ? undefined : lang, limit: 60 }),
    placeholderData: (prev) => prev,
  });
  const catById = new Map((cats.data ?? []).map((c) => [c.id, c]));
  const pick = (id: string) => {
    const next = new URLSearchParams(params);
    if (id) next.set("category", id);
    else next.delete("category");
    setParams(next, { replace: true });
  };

  return (
    <div className="space-y-5">
      <PageHeader
        icon={<BookOpen className="size-5" />}
        title={t("nav.kb", "Knowledge base")}
        subtitle={t("kb.subtitle", "Guides for bots, smart trades, exchanges and the platform.")}
        actions={user && <Link to="/support"><Button variant="secondary" size="sm" icon={<LifeBuoy className="size-4" />}>{t("kb.ask", "Ask support")}</Button></Link>}
      />
      <div className="flex flex-wrap items-center gap-3">
        <Input className="w-full max-w-md" value={q} onChange={(e) => setQ(e.target.value)} placeholder={t("kb.search", "Search articles…")} prefix={<Search className="size-4" />} />
        <Segmented size="xs" value={lang} onChange={setLang} options={[{ value: "all", label: t("common.all", "All") }, { value: "en", label: "English" }, { value: "ar", label: "العربية" }]} />
      </div>
      <div className="flex flex-wrap gap-2">
        {[{ id: "", label: t("kb.all_topics", "All topics"), count: undefined as number | undefined }, ...(cats.data ?? []).map((c) => ({ id: String(c.id), label: (uiLang === "ar" && c.title_ar) || c.title, count: c.post_count }))].map((c) => (
          <button
            key={c.id || "all"}
            type="button"
            onClick={() => pick(c.id)}
            className={cn("rounded-full border px-3 py-1.5 text-sm transition-colors", category === c.id ? "border-primary bg-primary-soft text-fg" : "border-line text-muted hover:text-fg")}
          >
            {c.label}
            {c.count !== undefined && <span className="num ms-1.5 text-xs text-muted">{c.count}</span>}
          </button>
        ))}
      </div>
      {posts.isLoading ? (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-72" />)}</div>
      ) : !posts.data?.length ? (
        <Card><EmptyState icon={<BookOpen className="size-6" />} title={t("kb.empty", "No articles found")} body={dq ? t("kb.empty_q", "Try a different search.") : undefined} /></Card>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {posts.data.map((p) => <PostCard key={p.id} post={p} category={p.category_id ? catById.get(p.category_id) : undefined} />)}
        </div>
      )}
    </div>
  );
}
