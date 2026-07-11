import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { getIdea, retryIdea } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import type {
  DimensionScore,
  EvaluationScores,
  IdeaResponse,
} from "@/types";
import { AppLayout } from "@/components/app-layout";
import {
  IdeaStatusBadge,
  InputDecisionBadge,
  AdminActionBadge,
  PayoutStatusBadge,
} from "@/components/idea-status-badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import {
  confidenceLabel,
  dimensionLabel,
  duplicateVerdictLabel,
  fieldLabel,
  formatAmount,
  formatDateTime,
  truncateContent,
} from "@/lib/idea-display";

const DIMENSION_KEYS: (keyof EvaluationScores)[] = [
  "demand_breadth",
  "pain_intensity",
  "willingness_to_pay",
  "feasibility",
  "novelty",
];

function isProcessing(status: string): boolean {
  return ["pending", "evaluating", "embedding", "checking_duplicate"].includes(
    status,
  );
}

export function IdeaDetailPage() {
  const { publicId } = useParams<{ publicId: string }>();
  const { clearAuth } = useAuth();
  const navigate = useNavigate();

  const [idea, setIdea] = useState<IdeaResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retrying, setRetrying] = useState(false);
  const [retryError, setRetryError] = useState<string | null>(null);

  const fetchIdea = useCallback(
    (signal?: AbortSignal) => {
      if (!publicId) return;
      setLoading(true);
      setError(null);
      getIdea(publicId, signal)
        .then((data) => setIdea(data))
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (err instanceof ApiError && err.status === 401) {
            clearAuth();
            navigate("/login", { replace: true });
            return;
          }
          if (err instanceof ApiError && err.status === 404) {
            setError("点子不存在或不可访问");
          } else if (err instanceof ApiError && err.status === 403) {
            setError("无权限查看此点子");
          } else {
            setError(
              err instanceof ApiError ? err.message : "加载失败，请稍后重试",
            );
          }
        })
        .finally(() => setLoading(false));
    },
    [publicId, clearAuth, navigate],
  );

  useEffect(() => {
    const controller = new AbortController();
    fetchIdea(controller.signal);
    return () => controller.abort();
  }, [fetchIdea]);

  async function handleRetry() {
    if (!publicId || !idea) return;
    setRetrying(true);
    setRetryError(null);
    try {
      const updated = await retryIdea(publicId);
      setIdea(updated);
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          clearAuth();
          navigate("/login", { replace: true });
          return;
        }
        setRetryError(err.message);
      } else {
        setRetryError("重试失败，请稍后重试");
      }
    } finally {
      setRetrying(false);
    }
  }

  function handleManualRefresh() {
    fetchIdea();
  }

  if (loading) {
    return (
      <AppLayout>
        <div className="flex items-center justify-center py-12">
          <p className="text-muted-foreground">加载中...</p>
        </div>
      </AppLayout>
    );
  }

  if (error) {
    return (
      <AppLayout>
        <div className="mb-4">
          <Link
            to="/ideas"
            className="text-sm text-muted-foreground transition-colors hover:text-foreground"
          >
            ← 返回列表
          </Link>
        </div>
        <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      </AppLayout>
    );
  }

  if (!idea) return null;

  const showRetry =
    idea.processing_status === "failed" && idea.retry_count < 3;
  const processing = isProcessing(idea.processing_status);

  return (
    <AppLayout>
      <div className="mb-4">
        <Link
          to="/ideas"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← 返回列表
        </Link>
      </div>

      {/* 基础信息 */}
      <Card className="mb-4">
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-lg">
              {idea.generated_title ?? truncateContent(idea.raw_content)}
            </CardTitle>
            <IdeaStatusBadge status={idea.processing_status} />
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <p className="text-sm font-medium">用户原始投稿</p>
            <p className="whitespace-pre-wrap text-sm text-muted-foreground">
              {idea.raw_content}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
            <div>
              <dt className="text-muted-foreground">提交时间</dt>
              <dd>{formatDateTime(idea.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">重试次数</dt>
              <dd>{idea.retry_count}</dd>
            </div>
            {idea.input_decision && (
              <div>
                <dt className="text-muted-foreground">输入结论</dt>
                <dd>
                  <InputDecisionBadge decision={idea.input_decision} />
                </dd>
              </div>
            )}
          </dl>
        </CardContent>
      </Card>

      {/* 处理中状态 */}
      {processing && (
        <Card className="mb-4">
          <CardContent className="flex items-center justify-between p-4">
            <p className="text-sm text-muted-foreground">
              AI 正在处理中，请稍后刷新查看结果。
            </p>
            <Button variant="outline" size="sm" onClick={handleManualRefresh}>
              刷新
            </Button>
          </CardContent>
        </Card>
      )}

      {/* AI 门禁 */}
      {idea.input_decision && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">AI 门禁</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <div className="flex items-center gap-2">
              <InputDecisionBadge decision={idea.input_decision} />
            </div>
            {idea.decision_reason && (
              <p className="text-sm text-muted-foreground">
                {idea.decision_reason}
              </p>
            )}
            {idea.input_decision === "clarify" && idea.clarification_question && (
              <div className="rounded-md bg-amber-50 px-4 py-3">
                <p className="text-sm text-amber-700">
                  {idea.clarification_question}
                </p>
                <Button variant="outline" size="sm" asChild className="mt-2">
                  <Link to="/ideas/new">重新提交点子</Link>
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 五维评分 */}
      {idea.evaluation && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">五维评分</CardTitle>
            <CardDescription>AI 对商业价值的五个维度评估</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {DIMENSION_KEYS.map((key) => {
              const dim = idea.evaluation![key] as DimensionScore;
              return (
                <div key={key} className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {dimensionLabel(key)}
                    </span>
                    <span className="text-sm">
                      {dim.score} / 5
                    </span>
                  </div>
                  <p className="text-sm text-muted-foreground">{dim.reason}</p>
                  <div className="flex flex-wrap gap-2 text-xs text-muted-foreground">
                    <span>置信度：{confidenceLabel(dim.confidence)}</span>
                    <span>
                      证据字段：
                      {dim.evidence_fields.map(fieldLabel).join("、")}
                    </span>
                  </div>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {/* 查重结果 */}
      {idea.duplicate_result && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">查重结果</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <p className="text-sm font-medium">
              {duplicateVerdictLabel(idea.duplicate_result.verdict)}
            </p>
            <p className="text-sm text-muted-foreground">
              {idea.duplicate_result.reason}
            </p>
            {idea.duplicate_result.same_aspects.length > 0 && (
              <div className="text-sm">
                <span className="text-muted-foreground">相同点：</span>
                {idea.duplicate_result.same_aspects.map(fieldLabel).join("、")}
              </div>
            )}
            {idea.duplicate_result.different_aspects.length > 0 && (
              <div className="text-sm">
                <span className="text-muted-foreground">不同点：</span>
                {idea.duplicate_result.different_aspects
                  .map(fieldLabel)
                  .join("、")}
              </div>
            )}
            {idea.duplicate_result.matched_public_id && (
              <Button variant="outline" size="sm" asChild>
                <Link to={`/ideas/${idea.duplicate_result.matched_public_id}/summary`}>
                  查看匹配点子摘要
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {/* 红包与管理员状态 */}
      {idea.processing_status === "completed" && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="text-base">红包与管理员状态</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3">
            <dl className="grid grid-cols-2 gap-2 text-sm sm:grid-cols-3">
              <div>
                <dt className="text-muted-foreground">商业评分</dt>
                <dd>
                  {idea.commercial_score !== null
                    ? idea.commercial_score
                    : "尚未生成"}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">基础金额</dt>
                <dd>{formatAmount(idea.base_amount)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">重复扣减</dt>
                <dd>{formatAmount(idea.duplicate_deduction)}</dd>
              </div>
              <div>
                <dt className="text-muted-foreground">最终金额</dt>
                <dd className="font-semibold">
                  {formatAmount(idea.final_amount)}
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">管理员操作</dt>
                <dd>
                  <AdminActionBadge action={idea.admin_action} />
                </dd>
              </div>
              <div>
                <dt className="text-muted-foreground">打款状态</dt>
                <dd>
                  <PayoutStatusBadge status={idea.payout_status} />
                </dd>
              </div>
            </dl>
            {idea.payout && (
              <div className="space-y-1 border-t pt-3 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">模拟流水号</span>
                  <span className="font-mono">{idea.payout.reference}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">模拟打款金额</span>
                  <span>{formatAmount(idea.payout.amount)}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">确认时间</span>
                  <span>{formatDateTime(idea.payout.confirmed_at)}</span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 重试 */}
      {showRetry && (
        <Card className="mb-4">
          <CardContent className="space-y-3 p-4">
            {retryError && (
              <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {retryError}
              </div>
            )}
            <div className="flex items-center justify-between">
              <p className="text-sm text-muted-foreground">
                处理失败，可重试（已重试 {idea.retry_count} 次，上限 3 次）
              </p>
              <Button
                variant="outline"
                size="sm"
                onClick={handleRetry}
                disabled={retrying}
              >
                {retrying ? "重试中..." : "重试处理"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}
    </AppLayout>
  );
}
