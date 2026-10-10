import { useMemo } from "react";
import { Link, useParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Eye } from "lucide-react";
import { useI18n, useT } from "../i18n";
import { v2 } from "../lib/api";
import type { KbCategory, KbPost as Post } from "../lib/types";
import { fmtDate } from "../lib/format";
import { sanitizeHtml } from "../lib/utils";
import { Card, ErrorState, Skeleton } from "../components/ui";
import { PostCard } from "./KnowledgeBase";

export default function KbPost() {
  const t = useT();
  const { lang } = useI18n();
  const { id } = useParams();
  const post = useQuery({ queryKey: ["kb", "post", id], queryFn: () => v2.get<Post>(`/kb/posts/${id}`), enabled: !!id });
  const cats = useQuery({ queryKey: ["kb", "cats"], queryFn: () => v2.get<KbCategory[]>("/kb/categories"), staleTime: 5 * 60_000 });
  const related = useQuery({
    queryKey: ["kb", "related", post.data?.category_id],
    queryFn: () => v2.get<Post[]>("/kb/posts", { category: post.data!.category_id!, limit: 4 }),
    enabled: !!post.data?.category_id,
  });
  const html = useMemo(() => sanitizeHtml(post.data?.content ?? ""), [post.data?.content]);
  const cat = cats.data?.find((c) => c.id === post.data?.category_id);
  const back = <ArrowLeft className="size-4 rtl:rotate-180" />;

  if (post.isError) return <Card><ErrorState error={post.error} onRetry={() => post.refetch()} /></Card>;
  if (!post.data) return <Skeleton className="mx-auto h-[70vh] max-w-3xl" />;
  const p = post.data;
  const more = (related.data ?? []).filter((r) => r.id !== p.id).slice(0, 3);

  return (
    <div className="mx-auto max-w-3xl space-y-6">
      <Link to={cat ? `/kb?category=${cat.id}` : "/kb"} className="inline-flex items-center gap-1.5 text-sm text-muted hover:text-fg">
        {back}
        {cat ? (lang === "ar" && cat.title_ar) || cat.title : t("nav.kb", "Knowledge base")}
      </Link>
      <article dir={p.lang === "ar" ? "rtl" : "ltr"} className="space-y-5">
        <header>
          <h1 className="text-2xl font-bold tracking-tight text-fg sm:text-3xl">{p.title}</h1>
          <p className="mt-2 flex flex-wrap items-center gap-2 text-sm text-muted">
            <span>{p.writer}</span>·<span>{fmtDate(p.created_at)}</span>·<span className="inline-flex items-center gap-1"><Eye className="size-3.5" />{p.views}</span>
          </p>
        </header>
        {p.img && <img src={p.img} alt="" className="w-full rounded-2xl border border-line object-cover" />}
        <Card className="p-5 sm:p-8">
          <div className="prose-pt" dangerouslySetInnerHTML={{ __html: html }} />
        </Card>
      </article>
      {!!more.length && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-fg">{t("kb.related", "Related articles")}</h2>
          <div className="grid gap-4 sm:grid-cols-3">{more.map((r) => <PostCard key={r.id} post={r} category={cat} />)}</div>
        </section>
      )}
    </div>
  );
}
