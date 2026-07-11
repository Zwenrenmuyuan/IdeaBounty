import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { listIdeas, PAGE_SIZE } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import type { IdeaSummary } from "@/types";
import { AppLayout } from "@/components/app-layout";
import { IdeaStatusBadge, InputDecisionBadge } from "@/components/idea-status-badge";
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
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-xl font-semibold">我的投稿</h1>
        <Button asChild size="sm">
          <Link to="/ideas/new">提交点子</Link>
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
        <Card>
          <CardHeader>
            <CardTitle>还没有投稿</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            <p className="text-sm text-muted-foreground">
              提交你的第一个商业点子，获取 AI 评估和红包估算。
            </p>
            <Button asChild>
              <Link to="/ideas/new">提交第一个点子</Link>
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
              <Card className="transition-colors hover:bg-accent/50">
                <CardContent className="flex flex-col gap-2 p-4">
                  <div className="flex items-start justify-between gap-2">
                    <p className="font-medium line-clamp-1">
                      {idea.generated_title ?? truncateContent(idea.raw_content)}
                    </p>
                  </div>
                  <div className="flex flex-wrap items-center gap-2 text-sm text-muted-foreground">
                    <IdeaStatusBadge status={idea.processing_status} />
                    {idea.input_decision && (
                      <InputDecisionBadge decision={idea.input_decision} />
                    )}
                    <span>{formatDateTime(idea.created_at)}</span>
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
