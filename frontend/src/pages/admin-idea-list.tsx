import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ADMIN_PAGE_SIZE,
  getAdminSummary,
  listAdminIdeas,
} from "@/api/admin";
import { AppLayout } from "@/components/app-layout";
import {
  AdminActionBadge,
  IdeaStatusBadge,
  InputDecisionBadge,
} from "@/components/idea-status-badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useAuth } from "@/hooks/use-auth";
import {
  duplicateVerdictLabel,
  formatAmount,
  formatDateTime,
} from "@/lib/idea-display";
import { ApiError } from "@/types";
import type { AdminIdeaListItem, AdminSummary } from "@/types";

const SUMMARY_ITEMS: {
  key: keyof AdminSummary;
  label: string;
  amount?: boolean;
}[] = [
  { key: "total_submissions", label: "投稿总数" },
  { key: "completed_accepts", label: "有效投稿" },
  { key: "duplicate_count", label: "重复投稿" },
  { key: "estimated_total", label: "估值总额", amount: true },
  { key: "confirmed_payout_count", label: "已确认笔数" },
  { key: "simulated_payout_total", label: "模拟打款总额", amount: true },
];

export function AdminIdeaListPage() {
  const { clearAuth } = useAuth();
  const navigate = useNavigate();
  const [summary, setSummary] = useState<AdminSummary | null>(null);
  const [items, setItems] = useState<AdminIdeaListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const handleRequestError = useCallback(
    (error: unknown) => {
      if (error instanceof DOMException && error.name === "AbortError") return;
      if (error instanceof ApiError && error.status === 401) {
        clearAuth();
        navigate("/login", { replace: true });
        return;
      }
      if (error instanceof ApiError && error.status === 403) {
        navigate("/ideas", { replace: true });
        return;
      }
      setError(error instanceof ApiError ? error.message : "加载失败，请稍后重试");
    },
    [clearAuth, navigate],
  );

  const fetchPage = useCallback(
    (pageOffset: number) => {
      const controller = new AbortController();
      setLoading(true);
      setError(null);
      Promise.all([
        getAdminSummary(controller.signal),
        listAdminIdeas(pageOffset, ADMIN_PAGE_SIZE, controller.signal),
      ])
        .then(([summaryResponse, listResponse]) => {
          setSummary(summaryResponse);
          setItems(listResponse.items);
          setTotal(listResponse.total);
          setOffset(listResponse.offset);
        })
        .catch(handleRequestError)
        .finally(() => setLoading(false));
      return controller;
    },
    [handleRequestError],
  );

  useEffect(() => {
    const controller = fetchPage(0);
    return () => controller.abort();
  }, [fetchPage]);

  const hasPrev = offset > 0;
  const hasNext = offset + items.length < total;

  return (
    <AppLayout>
      <div className="mb-5">
        <h1 className="text-xl font-semibold">管理后台</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          查看投稿评估结果并完成一次性最终处理。
        </p>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      )}

      {error && !loading && (
        <div role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      {!loading && !error && summary && (
        <>
          <section aria-label="后台汇总" className="mb-6 grid grid-cols-2 gap-3 sm:grid-cols-3">
            {SUMMARY_ITEMS.map(({ key, label, amount }) => (
              <Card key={key}>
                <CardContent className="p-4">
                  <p className="text-xs text-muted-foreground">{label}</p>
                  <p className="mt-1 text-xl font-semibold">
                    {amount ? formatAmount(summary[key]) : summary[key]}
                  </p>
                </CardContent>
              </Card>
            ))}
          </section>

          <section aria-labelledby="admin-ideas-heading">
            <h2 id="admin-ideas-heading" className="mb-3 text-lg font-semibold">
              全部投稿
            </h2>

            {items.length === 0 ? (
              <Card>
                <CardHeader>
                  <CardTitle className="text-base">暂无投稿</CardTitle>
                </CardHeader>
              </Card>
            ) : (
              <div className="space-y-3">
                {items.map((idea) => (
                  <Link
                    key={idea.public_id}
                    to={`/admin/ideas/${idea.public_id}`}
                    className="block"
                  >
                    <Card className="transition-colors hover:bg-accent/50">
                      <CardContent className="space-y-3 p-4">
                        <div className="flex flex-col gap-1 sm:flex-row sm:items-start sm:justify-between">
                          <div className="min-w-0">
                            <p className="truncate font-medium">
                              {idea.generated_title ?? "尚未生成标题"}
                            </p>
                            <p className="text-sm text-muted-foreground">
                              投稿用户：{idea.username}
                            </p>
                          </div>
                          <span className="shrink-0 text-xs text-muted-foreground">
                            {formatDateTime(idea.created_at)}
                          </span>
                        </div>
                        <div className="flex flex-wrap items-center gap-2 text-sm">
                          <IdeaStatusBadge status={idea.processing_status} />
                          <InputDecisionBadge decision={idea.input_decision} />
                          <AdminActionBadge action={idea.admin_action} />
                          {idea.duplicate_verdict && (
                            <span className="text-muted-foreground">
                              {duplicateVerdictLabel(idea.duplicate_verdict)}
                            </span>
                          )}
                          <span className="text-muted-foreground">
                            商业分：{idea.commercial_score ?? "—"}
                          </span>
                          <span className="font-medium">
                            {formatAmount(idea.final_amount)}
                          </span>
                        </div>
                      </CardContent>
                    </Card>
                  </Link>
                ))}

                <div className="flex items-center justify-between gap-2 pt-2">
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!hasPrev}
                    onClick={() => fetchPage(Math.max(0, offset - ADMIN_PAGE_SIZE))}
                  >
                    上一页
                  </Button>
                  <span className="text-center text-sm text-muted-foreground">
                    {offset + 1}–{offset + items.length} / 共 {total} 条
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    disabled={!hasNext}
                    onClick={() => fetchPage(offset + ADMIN_PAGE_SIZE)}
                  >
                    下一页
                  </Button>
                </div>
              </div>
            )}
          </section>
        </>
      )}
    </AppLayout>
  );
}
