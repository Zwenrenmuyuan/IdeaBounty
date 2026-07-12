import { useCallback, useEffect, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ArrowLeft, ShieldCheck } from "lucide-react";
import { getPublicSummary } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import type { PublicIdeaSummary } from "@/types";
import { AppLayout } from "@/components/app-layout";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatDate } from "@/lib/idea-display";

export function IdeaSummaryPage() {
  const { publicId } = useParams<{ publicId: string }>();
  const { clearAuth } = useAuth();
  const navigate = useNavigate();

  const [summary, setSummary] = useState<PublicIdeaSummary | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSummary = useCallback(
    (signal?: AbortSignal) => {
      if (!publicId) return;
      setLoading(true);
      setError(null);
      getPublicSummary(publicId, signal)
        .then((data) => setSummary(data))
        .catch((err) => {
          if (err instanceof DOMException && err.name === "AbortError") return;
          if (err instanceof ApiError && err.status === 401) {
            clearAuth();
            navigate("/login", { replace: true });
            return;
          }
          if (err instanceof ApiError && err.status === 404) {
            setError("点子不存在或不可公开");
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
    fetchSummary(controller.signal);
    return () => controller.abort();
  }, [fetchSummary]);

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

  if (!summary) return null;

  return (
    <AppLayout>
      <div className="mb-4">
        <Link
          to="/ideas"
          className="inline-flex items-center gap-1.5 text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          <ArrowLeft className="size-4" />
          返回列表
        </Link>
      </div>

      <Card className="overflow-hidden">
        <div className="h-1 bg-gradient-to-r from-amber-400 to-primary/70" />
        <CardHeader>
          <CardTitle className="text-lg">
            {summary.generated_title ?? "未公开"}
          </CardTitle>
          <CardDescription className="flex items-center gap-1.5">
            <ShieldCheck className="size-4 text-emerald-600" />
            脱敏摘要 · {formatDate(summary.created_date)}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-1">
            <p className="text-sm font-medium">目标用户</p>
            <p className="text-sm text-muted-foreground">
              {summary.target_audience ?? "未公开"}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">痛点</p>
            <p className="text-sm text-muted-foreground">
              {summary.pain_point ?? "未公开"}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">场景背景</p>
            <p className="text-sm text-muted-foreground">
              {summary.context ?? "未公开"}
            </p>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-medium">是否提出方案</p>
            <Badge variant={summary.solution_present ? "success" : "secondary"}>
              {summary.solution_present ? "是" : "否"}
            </Badge>
          </div>
          {summary.solution_present && (
            <div className="space-y-1">
              <p className="text-sm font-medium">方案概述</p>
              <p className="text-sm text-muted-foreground">
                {summary.solution_outline ?? "未公开"}
              </p>
            </div>
          )}
        </CardContent>
      </Card>
    </AppLayout>
  );
}
