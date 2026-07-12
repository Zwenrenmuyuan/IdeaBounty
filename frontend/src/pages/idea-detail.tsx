import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Coins, RefreshCw, Sparkles, Trash2 } from "lucide-react";
import { deleteIdea, getIdea, retryIdea, supplementIdea } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import type {
  DimensionScore,
  EvaluationScores,
  IdeaResponse,
} from "@/types";
import { AppLayout } from "@/components/app-layout";
import {
  IdeaDisplayStatusBadge,
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
import { Textarea } from "@/components/ui/textarea";
import { ScoreMeter } from "@/components/score-meter";
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
  const [supplementContent, setSupplementContent] = useState("");
  const [supplementing, setSupplementing] = useState(false);
  const [supplementError, setSupplementError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const fetchIdea = useCallback(
    (signal?: AbortSignal) => {
      if (!publicId) return;
      setLoading(true);
      setError(null);
      getIdea(publicId, signal)
        .then((data) => {
          setIdea(data);
          if (data.input_decision === "clarify") {
            setSupplementContent(data.raw_content);
          }
        })
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

  async function handleSupplement() {
    if (!publicId) return;
    setSupplementing(true);
    setSupplementError(null);
    try {
      const updated = await supplementIdea(publicId, {
        raw_content: supplementContent,
      });
      setIdea(updated);
      if (updated.input_decision === "clarify") {
        setSupplementContent(updated.raw_content);
      }
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAuth();
        navigate("/login", { replace: true });
        return;
      }
      setSupplementError(
        err instanceof ApiError ? err.message : "提交补充失败，请稍后重试",
      );
    } finally {
      setSupplementing(false);
    }
  }

  async function handleDelete() {
    if (!publicId || !window.confirm("删除后无法恢复，确认删除这条投稿吗？")) {
      return;
    }
    setDeleting(true);
    setDeleteError(null);
    try {
      await deleteIdea(publicId);
      navigate("/ideas", { replace: true });
    } catch (err) {
      if (err instanceof ApiError && err.status === 401) {
        clearAuth();
        navigate("/login", { replace: true });
        return;
      }
      setDeleteError(
        err instanceof ApiError ? err.message : "删除失败，请稍后重试",
      );
    } finally {
      setDeleting(false);
    }
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
  const canDelete =
    idea.processing_status === "failed" ||
    (idea.processing_status === "completed" &&
      (idea.input_decision === "clarify" ||
        idea.input_decision === "reject"));

  return (
    <AppLayout>
      <div className="mb-5">
        <Link
          to="/ideas"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回列表
        </Link>
      </div>

      {/* 基础信息 */}
      <Card className="mb-5 overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-amber-400 via-amber-300 to-primary/70" />
        <CardHeader>
          <div className="flex items-start justify-between gap-2">
            <CardTitle className="text-xl leading-snug">
              {idea.generated_title ?? truncateContent(idea.raw_content)}
            </CardTitle>
            <IdeaDisplayStatusBadge
              status={idea.processing_status}
              decision={idea.input_decision}
            />
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
              <RefreshCw />
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
              <div className="space-y-3 rounded-xl border border-amber-200/80 bg-amber-50/80 px-4 py-4">
                <div>
                  <p className="text-xs font-medium uppercase tracking-wide text-amber-700">
                    请补充以下信息
                  </p>
                  <p className="mt-1 text-sm leading-6 text-amber-800">
                    {idea.clarification_question}
                  </p>
                </div>
                <div className="space-y-1.5">
                  <label htmlFor="supplement-content" className="text-sm font-medium">
                    完善投稿内容
                  </label>
                  <Textarea
                    id="supplement-content"
                    value={supplementContent}
                    onChange={(event) => setSupplementContent(event.target.value)}
                    maxLength={2000}
                    rows={7}
                    disabled={supplementing}
                  />
                  <p className="text-right text-xs text-muted-foreground">
                    {supplementContent.length} / 2000
                  </p>
                </div>
                {supplementError && (
                  <div className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
                    {supplementError}
                  </div>
                )}
                <Button
                  onClick={handleSupplement}
                  disabled={
                    supplementing ||
                    supplementContent.trim().length < 8 ||
                    supplementContent.length > 2000
                  }
                >
                  {supplementing ? "重新评估中..." : "提交补充并重新评估"}
                </Button>
              </div>
            )}
          </CardContent>
        </Card>
      )}

      {/* 五维评分 */}
      {idea.evaluation && (
        <Card className="mb-5">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-amber-600" />
              五维评分
            </CardTitle>
            <CardDescription>AI 对商业价值的五个维度评估</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            {DIMENSION_KEYS.map((key) => {
              const dim = idea.evaluation![key] as DimensionScore;
              return (
                <div key={key} className="rounded-xl border border-border/70 bg-muted/35 p-3.5">
                  <div className="flex items-center justify-between">
                    <span className="text-sm font-medium">
                      {dimensionLabel(key)}
                    </span>
                    <span className="font-semibold text-amber-700">
                      {dim.score} / 5
                    </span>
                  </div>
                  <ScoreMeter score={dim.score} className="my-2.5" />
                  <p className="text-sm leading-6 text-muted-foreground">{dim.reason}</p>
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
      {idea.processing_status === "completed" &&
        idea.input_decision === "accept" && (
          <Card className="mb-5 overflow-hidden border-amber-200/80 bg-gradient-to-br from-white to-reward-soft/70">
            <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <span className="flex size-8 items-center justify-center rounded-xl bg-amber-100 text-amber-700">
                <Coins className="size-4" />
              </span>
              红包与管理员状态
            </CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
            <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-3">
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
              <div className="rounded-xl bg-white/70 p-3 ring-1 ring-amber-100">
                <dt className="text-muted-foreground">最终金额</dt>
                <dd className="mt-1 text-xl font-semibold text-amber-700">
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
            {idea.admin_reason && (
              <div
                className={
                  idea.admin_action === "rejected"
                    ? "rounded-xl border border-destructive/15 bg-destructive/10 p-3.5"
                    : "rounded-xl border border-primary/10 bg-primary/5 p-3.5"
                }
              >
                <p className="text-sm font-medium">管理员说明</p>
                <p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">
                  {idea.admin_reason}
                </p>
              </div>
            )}
            {idea.payout && (
              <div className="space-y-1 border-t pt-3 text-sm">
                <div className="flex flex-col gap-1 sm:flex-row sm:justify-between">
                  <span className="text-muted-foreground">模拟流水号</span>
                  <span className="min-w-0 break-all font-mono sm:text-right">
                    {idea.payout.reference}
                  </span>
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

      {canDelete && (
        <div className="flex flex-col items-start gap-2 border-t border-border/70 pt-5 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <p className="text-sm font-medium">不再保留这条投稿？</p>
            <p className="text-xs text-muted-foreground">
              尚未形成有效评估结果的投稿可以永久删除。
            </p>
          </div>
          <Button
            variant="destructive"
            size="sm"
            onClick={handleDelete}
            disabled={deleting || supplementing}
          >
            <Trash2 />
            {deleting ? "删除中..." : "删除投稿"}
          </Button>
          {deleteError && (
            <p className="text-sm text-destructive">{deleteError}</p>
          )}
        </div>
      )}
    </AppLayout>
  );
}
