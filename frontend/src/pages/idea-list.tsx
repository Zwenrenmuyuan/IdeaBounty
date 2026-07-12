import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, Lightbulb, Plus, Sparkles } from "lucide-react";
import { listIdeas, PAGE_SIZE } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import type { IdeaSummary } from "@/types";
import { AppLayout } from "@/components/app-layout";
import { IdeaDisplayStatusBadge } from "@/components/idea-status-badge";
import {
  Card,
  CardContent,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { formatDateTime, truncateContent } from "@/lib/idea-display";

export function IdeaListPage() {
  const { clearAuth } = useAuth();
  const navigate = useNavigate();

  const [items, setItems] = useState<IdeaSummary[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(
    (pageOffset: number) => {
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      listIdeas(pageOffset, PAGE_SIZE, controller.signal)
        .then((resp) => {
          setItems(resp.items);
          setTotal(resp.total);
          setOffset(resp.offset);
        })
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (err instanceof ApiError && err.status === 401) {
            clearAuth();
            navigate("/login", { replace: true });
            return;
          }
          setError(err instanceof ApiError ? err.message : "加载失败，请稍后重试");
        })
        .finally(() => setLoading(false));
      return controller;
    },
    [clearAuth, navigate],
  );

  useEffect(() => {
    const controller = fetchPage(0);
    return () => controller.abort();
  }, [fetchPage]);

  const hasPrev = offset > 0;
  const hasNext = offset + items.length < total;

  return (
    <AppLayout>
      <div className="mb-7 flex items-end justify-between gap-4">
        <div>
          <p className="mb-1 text-sm font-medium text-amber-700">点子工作台</p>
          <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">我的投稿</h1>
          <p className="mt-1.5 text-sm text-muted-foreground">
            记录真实痛点，查看 AI 评估与红包处理进度。
          </p>
        </div>
        <Button asChild>
          <Link to="/ideas/new">
            <Plus />
            <span className="hidden sm:inline">提交点子</span>
            <span className="sm:hidden">提交</span>
          </Link>
        </Button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}

      {error && !loading && (
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <Card className="border-dashed bg-white/65 py-6 text-center">
          <CardHeader className="items-center">
            <span
              className={
                "mb-2 inline-flex size-12 items-center justify-center rounded-2xl " +
                "bg-reward-soft text-amber-700"
              }
            >
              <Lightbulb className="size-6" />
            </span>
            <CardTitle>还没有投稿</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              提交你的第一个商业点子，获取 AI 评估和红包估算。
            </p>
            <Button asChild>
              <Link to="/ideas/new">
                <Sparkles />
                提交第一个点子
              </Link>
            </Button>
          </CardContent>
        </Card>
      )}

      {!loading && !error && items.length > 0 && (
        <div className="space-y-3">
          {items.map((idea) => (
            <Link
              key={idea.public_id}
              to={`/ideas/${idea.public_id}`}
              className="block"
            >
              <Card
                className={
                  "group transition-all hover:-translate-y-0.5 hover:border-primary/20 " +
                  "hover:shadow-[0_12px_32px_rgba(30,41,59,0.09)]"
                }
              >
                <CardContent className="flex gap-3 p-4 sm:p-5">
                  <span
                    className={
                      "mt-0.5 hidden size-9 shrink-0 items-center justify-center rounded-xl " +
                      "bg-reward-soft text-amber-700 sm:inline-flex"
                    }
                  >
                    <Lightbulb className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1 space-y-2">
                  <div className="flex items-start justify-between gap-2">
                    <p className="line-clamp-1 font-medium transition-colors group-hover:text-primary">
                      {idea.generated_title ?? truncateContent(idea.raw_content)}
                    </p>
                    <ArrowRight
                      className={
                        "mt-0.5 size-4 shrink-0 text-muted-foreground transition-transform " +
                        "group-hover:translate-x-0.5 group-hover:text-primary"
                      }
                    />
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <IdeaDisplayStatusBadge
                      status={idea.processing_status}
                      decision={idea.input_decision}
                    />
                    <span>{formatDateTime(idea.created_at)}</span>
                  </div>
                  </div>
                </CardContent>
              </Card>
            </Link>
          ))}

          <div className="flex items-center justify-between pt-2">
            <Button
              variant="outline"
              size="sm"
              disabled={!hasPrev || loading}
              onClick={() => fetchPage(Math.max(0, offset - PAGE_SIZE))}
            >
              上一页
            </Button>
            <span className="text-sm text-muted-foreground">
              {offset + 1}–{offset + items.length} / 共 {total} 条
            </span>
            <Button
              variant="outline"
              size="sm"
              disabled={!hasNext || loading}
              onClick={() => fetchPage(offset + PAGE_SIZE)}
            >
              下一页
            </Button>
          </div>
        </div>
      )}
    </AppLayout>
  );
}
