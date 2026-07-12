import { useCallback, useEffect, useState, type FormEvent } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, Coins, Sparkles } from "lucide-react";
import { getAdminIdea, processAdminIdea } from "@/api/admin";
import { AppLayout } from "@/components/app-layout";
import {
  AdminActionBadge,
  IdeaStatusBadge,
  InputDecisionBadge,
  PayoutStatusBadge,
} from "@/components/idea-status-badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { ScoreMeter } from "@/components/score-meter";
import { useAuth } from "@/hooks/use-auth";
import {
  confidenceLabel,
  dimensionLabel,
  duplicateVerdictLabel,
  fieldLabel,
  formatAmount,
  formatDateTime,
  truncateContent,
} from "@/lib/idea-display";
import { ApiError } from "@/types";
import type {
  AdminAction,
  AdminIdeaDetailResponse,
  AdminIdeaProcessRequest,
  EvaluationScores,
} from "@/types";

const DIMENSION_KEYS: (keyof EvaluationScores)[] = [
  "demand_breadth",
  "pain_intensity",
  "willingness_to_pay",
  "feasibility",
  "novelty",
];

type ProcessChoice = Extract<AdminAction, "confirmed" | "adjusted" | "rejected">;

export function AdminIdeaDetailPage() {
  const { publicId } = useParams<{ publicId: string }>();
  const { clearAuth } = useAuth();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<AdminIdeaDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [choice, setChoice] = useState<ProcessChoice>("confirmed");
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [processError, setProcessError] = useState<string | null>(null);

  const handleAuthError = useCallback(
    (requestError: ApiError): boolean => {
      if (requestError.status === 401) {
        clearAuth();
        navigate("/login", { replace: true });
        return true;
      }
      if (requestError.status === 403) {
        navigate("/ideas", { replace: true });
        return true;
      }
      return false;
    },
    [clearAuth, navigate],
  );

  useEffect(() => {
    if (!publicId) return;
    const controller = new AbortController();
    setLoading(true);
    getAdminIdea(publicId, controller.signal)
      .then(setDetail)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === "AbortError") return;
        if (requestError instanceof ApiError && handleAuthError(requestError)) return;
        if (requestError instanceof ApiError && requestError.status === 404) {
          setError("点子不存在");
          return;
        }
        setError(requestError instanceof ApiError ? requestError.message : "加载失败，请稍后重试");
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [handleAuthError, publicId]);

  function buildPayload(): AdminIdeaProcessRequest | null {
    const normalizedReason = reason.trim();
    if (choice === "confirmed") return { action: "confirmed" };
    if (!normalizedReason) {
      setProcessError(choice === "adjusted" ? "调整金额时必须填写理由" : "驳回时必须填写理由");
      return null;
    }
    if (choice === "rejected") {
      return { action: "rejected", reason: normalizedReason };
    }
    const parsedAmount = Number(amount);
    if (amount.trim() === "" || !Number.isFinite(parsedAmount) || parsedAmount < 0 || parsedAmount > 100) {
      setProcessError("调整金额必须在 0–100 元之间");
      return null;
    }
    return { action: "adjusted", amount: parsedAmount, reason: normalizedReason };
  }

  async function handleProcess(event: FormEvent) {
    event.preventDefault();
    if (!publicId || !detail) return;
    setProcessError(null);
    const payload = buildPayload();
    if (!payload) return;
    if (!window.confirm("该操作提交后不能修改，确认继续吗？")) return;

    setSubmitting(true);
    try {
      const updated = await processAdminIdea(publicId, payload);
      setDetail(updated);
      setReason("");
      setAmount("");
    } catch (requestError) {
      if (requestError instanceof ApiError && handleAuthError(requestError)) return;
      setProcessError(
        requestError instanceof ApiError
          ? requestError.message
          : "处理失败，请稍后重试",
      );
    } finally {
      setSubmitting(false);
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

  if (error || !detail) {
    return (
      <AppLayout>
        <Link
          to="/admin"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回管理后台
        </Link>
        <div role="alert" className="mt-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error ?? "点子不存在"}
        </div>
      </AppLayout>
    );
  }

  const { idea } = detail;
  const canProcess =
    idea.processing_status === "completed" &&
    idea.input_decision === "accept" &&
    idea.admin_action === null;

  return (
    <AppLayout>
      <div className="mb-4">
        <Link to="/admin" className="text-sm text-muted-foreground hover:text-foreground">
          ← 返回管理后台
        </Link>
      </div>

      <Card className="mb-5 overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-amber-400 via-amber-300 to-primary/70" />
        <CardHeader>
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
            <div className="min-w-0">
              <CardTitle className="break-words text-lg">
                {idea.generated_title ?? truncateContent(idea.raw_content)}
              </CardTitle>
              <CardDescription className="mt-1">投稿用户：{detail.username}</CardDescription>
            </div>
            <div className="flex shrink-0 flex-wrap gap-2">
              <IdeaStatusBadge status={idea.processing_status} />
              <InputDecisionBadge decision={idea.input_decision} />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          <div>
            <p className="text-sm font-medium">用户原始投稿</p>
            <p className="mt-1 whitespace-pre-wrap break-words text-sm text-muted-foreground">
              {idea.raw_content}
            </p>
          </div>
          <dl className="grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-muted-foreground">提交时间</dt>
              <dd>{formatDateTime(idea.created_at)}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">商业评分</dt>
              <dd>{idea.commercial_score ?? "—"}</dd>
            </div>
            <div>
              <dt className="text-muted-foreground">规则金额</dt>
              <dd>{formatAmount(idea.base_amount)}</dd>
            </div>
            <div className="rounded-xl bg-reward-soft p-3">
              <dt className="text-muted-foreground">当前金额</dt>
              <dd className="mt-1 text-lg font-semibold text-amber-700">
                {formatAmount(idea.final_amount)}
              </dd>
            </div>
          </dl>
        </CardContent>
      </Card>

      {idea.decision_reason && (
        <Card className="mb-4">
          <CardHeader><CardTitle className="text-base">AI 输入判断</CardTitle></CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground">{idea.decision_reason}</p>
          </CardContent>
        </Card>
      )}

      {idea.evaluation && (
        <Card className="mb-4">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Sparkles className="size-4 text-amber-600" />
              五维评分
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {DIMENSION_KEYS.map((key) => {
              const dimension = idea.evaluation![key];
              return (
                <div key={key} className="rounded-xl border border-border/70 bg-muted/35 p-3.5">
                  <div className="flex items-center justify-between gap-4 text-sm">
                    <span className="font-medium">{dimensionLabel(key)}</span>
                    <span className="font-semibold text-amber-700">{dimension.score} / 5</span>
                  </div>
                  <ScoreMeter score={dimension.score} className="my-2.5" />
                  <p className="text-sm leading-6 text-muted-foreground">{dimension.reason}</p>
                  <p className="text-xs text-muted-foreground">
                    置信度：{confidenceLabel(dimension.confidence)}；证据：
                    {dimension.evidence_fields.map(fieldLabel).join("、")}
                  </p>
                </div>
              );
            })}
          </CardContent>
        </Card>
      )}

      {idea.duplicate_result && (
        <Card className="mb-4">
          <CardHeader><CardTitle className="text-base">查重结果</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            <p className="font-medium">{duplicateVerdictLabel(idea.duplicate_result.verdict)}</p>
            <p className="text-muted-foreground">{idea.duplicate_result.reason}</p>
            {idea.duplicate_result.same_aspects.length > 0 && (
              <p><span className="text-muted-foreground">相同点：</span>{idea.duplicate_result.same_aspects.map(fieldLabel).join("、")}</p>
            )}
            {idea.duplicate_result.different_aspects.length > 0 && (
              <p><span className="text-muted-foreground">不同点：</span>{idea.duplicate_result.different_aspects.map(fieldLabel).join("、")}</p>
            )}
            {idea.duplicate_result.matched_public_id && (
              <Button asChild variant="outline" size="sm">
                <Link to={`/ideas/${idea.duplicate_result.matched_public_id}/summary`}>
                  查看匹配点子摘要
                </Link>
              </Button>
            )}
          </CardContent>
        </Card>
      )}

      {canProcess ? (
        <Card className="mb-4 border-amber-200/80 bg-gradient-to-br from-white to-reward-soft/60">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-base">
              <Coins className="size-4 text-amber-700" />
              最终处理
            </CardTitle>
            <CardDescription>每条投稿只能处理一次，提交后不可修改。</CardDescription>
          </CardHeader>
          <CardContent>
            <form className="space-y-4" onSubmit={handleProcess}>
              {processError && (
                <div role="alert" className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                  {processError}
                </div>
              )}
              <fieldset className="grid gap-2 sm:grid-cols-3" disabled={submitting}>
                <legend className="sr-only">选择最终处理方式</legend>
                {([
                  ["confirmed", "确认规则金额"],
                  ["adjusted", "调整后确认"],
                  ["rejected", "驳回投稿"],
                ] as const).map(([value, label]) => (
                  <label
                    key={value}
                    className={
                      "flex cursor-pointer items-center gap-2 rounded-xl border p-3 " +
                      `text-sm transition-colors ${
                        choice === value
                          ? "border-primary/40 bg-primary/5 text-primary"
                          : "bg-white/60 hover:bg-white"
                      }`
                    }
                  >
                    <input
                      type="radio"
                      name="admin-action"
                      value={value}
                      checked={choice === value}
                      onChange={() => {
                        setChoice(value);
                        setProcessError(null);
                      }}
                    />
                    {label}
                  </label>
                ))}
              </fieldset>

              {choice === "adjusted" && (
                <div className="space-y-2">
                  <Label htmlFor="amount">调整金额（0–100 元）</Label>
                  <Input
                    id="amount"
                    type="number"
                    min="0"
                    max="100"
                    step="0.01"
                    value={amount}
                    onChange={(event) => setAmount(event.target.value)}
                    disabled={submitting}
                    required
                  />
                </div>
              )}

              {choice !== "confirmed" && (
                <div className="space-y-2">
                  <Label htmlFor="reason">{choice === "adjusted" ? "调整理由" : "驳回理由"}</Label>
                  <Textarea
                    id="reason"
                    maxLength={300}
                    value={reason}
                    onChange={(event) => setReason(event.target.value)}
                    disabled={submitting}
                    required
                  />
                  <p className="text-right text-xs text-muted-foreground">{reason.length} / 300</p>
                </div>
              )}

              <Button type="submit" variant={choice === "rejected" ? "destructive" : "default"} disabled={submitting}>
                {submitting ? "提交中..." : "提交最终处理"}
              </Button>
            </form>
          </CardContent>
        </Card>
      ) : (
        <Card className="mb-4">
          <CardHeader><CardTitle className="text-base">处理结果</CardTitle></CardHeader>
          <CardContent className="space-y-3 text-sm">
            {idea.admin_action ? (
              <>
                <div className="flex flex-wrap items-center gap-2">
                  <AdminActionBadge action={idea.admin_action} />
                  <PayoutStatusBadge status={idea.payout_status} />
                </div>
                <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                  <div><dt className="text-muted-foreground">最终金额</dt><dd className="font-semibold">{formatAmount(idea.final_amount)}</dd></div>
                  <div><dt className="text-muted-foreground">处理时间</dt><dd>{detail.admin_processed_at ? formatDateTime(detail.admin_processed_at) : "—"}</dd></div>
                  <div><dt className="text-muted-foreground">处理理由</dt><dd>{detail.admin_reason ?? "—"}</dd></div>
                </dl>
                {idea.payout && (
                  <div className="border-t pt-3">
                    <p>模拟流水号：<span className="break-all font-mono">{idea.payout.reference}</span></p>
                    <p>确认金额：{formatAmount(idea.payout.amount)}</p>
                  </div>
                )}
              </>
            ) : (
              <p className="text-muted-foreground">当前投稿尚未完成有效评估，暂不可进行最终处理。</p>
            )}
          </CardContent>
        </Card>
      )}
    </AppLayout>
  );
}
