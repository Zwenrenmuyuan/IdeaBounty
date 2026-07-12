import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, CheckCircle2, Send, Sparkles, Users } from "lucide-react";
import { createIdea } from "@/api/ideas";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import { AppLayout } from "@/components/app-layout";
import { Button } from "@/components/ui/button";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const MIN_LENGTH = 8;
const MAX_LENGTH = 2000;

export function IdeaCreatePage() {
  const { clearAuth } = useAuth();
  const navigate = useNavigate();

  const [content, setContent] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastContent, setLastContent] = useState<string | null>(null);
  const [lastKey, setLastKey] = useState<string | null>(null);
  const [keyInvalidated, setKeyInvalidated] = useState(false);

  const trimmedLength = content.trim().length;
  const charCount = content.length;
  const valid = trimmedLength >= MIN_LENGTH && content.length <= MAX_LENGTH;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    if (content.trim().length < MIN_LENGTH) {
      setError(`投稿内容去除首尾空白后至少需要 ${MIN_LENGTH} 个字符`);
      return;
    }
    if (content.length > MAX_LENGTH) {
      setError(`投稿内容不能超过 ${MAX_LENGTH} 个字符`);
      return;
    }

    let key: string;
    if (lastKey && lastContent === content && !keyInvalidated) {
      key = lastKey;
    } else {
      key = crypto.randomUUID();
      setLastKey(key);
      setLastContent(content);
      setKeyInvalidated(false);
    }

    setSubmitting(true);
    setError(null);
    try {
      const idea = await createIdea(
        { submission_key: key, raw_content: content },
      );
      navigate(`/ideas/${idea.public_id}`, { replace: true });
    } catch (err) {
      if (err instanceof ApiError) {
        if (err.status === 401) {
          clearAuth();
          navigate("/login", { replace: true });
          return;
        }
        if (err.status === 409) {
          setKeyInvalidated(true);
        }
        setError(err.message);
      } else if (err instanceof DOMException && err.name === "AbortError") {
        return;
      } else {
        setError("提交失败，请稍后重试");
      }
    } finally {
      setSubmitting(false);
    }
  }

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

      <div className="mb-7">
        <p className="mb-1 text-sm font-medium text-amber-700">新投稿</p>
        <h1 className="text-2xl font-semibold tracking-tight sm:text-3xl">
          说说你发现的问题
        </h1>
        <p className="mt-1.5 text-sm text-muted-foreground">
          不必写商业计划，一段真实、具体的描述就够了。
        </p>
      </div>

      <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Sparkles className="size-5 text-amber-600" />
              投稿内容
            </CardTitle>
            <CardDescription>
              用一段话描述你发现的商业痛点或点子。AI 将对内容进行评估、查重和红包估算。
            </CardDescription>
          </CardHeader>
          <form onSubmit={handleSubmit}>
          <CardContent className="space-y-4">
            {error && (
              <div className="rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive">
                {error}
              </div>
            )}
            <div className="space-y-2">
              <Label htmlFor="content">投稿原文</Label>
              <Textarea
                id="content"
                placeholder="描述你发现的商业机会、用户痛点或解决方案…"
                value={content}
                onChange={(e) => setContent(e.target.value)}
                rows={8}
                className="min-h-56"
                disabled={submitting}
                maxLength={MAX_LENGTH}
              />
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>
                  {trimmedLength < MIN_LENGTH
                    ? `还需 ${MIN_LENGTH - trimmedLength} 个字符`
                    : "已满足最低长度"}
                </span>
                <span>
                  {charCount} / {MAX_LENGTH}
                </span>
              </div>
            </div>
            <p className="text-sm text-muted-foreground">
              AI 处理可能需要一些时间，请耐心等待。
            </p>
          </CardContent>
          <CardFooter className="flex gap-4">
            <Button type="submit" disabled={submitting || !valid}>
              {!submitting && <Send />}
              {submitting ? "提交中..." : "提交点子"}
            </Button>
            {submitting ? (
              <Button variant="outline" disabled>
                取消
              </Button>
            ) : (
              <Button variant="outline" asChild>
                <Link to="/ideas">取消</Link>
              </Button>
            )}
          </CardFooter>
          </form>
        </Card>
        <Card className="bg-primary text-primary-foreground lg:sticky lg:top-24">
          <CardHeader>
            <CardTitle className="text-base">写得更清楚的小提示</CardTitle>
            <CardDescription className="text-primary-foreground/65">
              只写你确定的信息，不需要编造市场数据。
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 text-sm">
            <div className="flex gap-3">
              <Users className="mt-0.5 size-4 shrink-0 text-amber-300" />
              <p>
                <span className="font-medium">面向谁：</span>
                <span className="text-primary-foreground/70">谁经常遇到这个问题？</span>
              </p>
            </div>
            <div className="flex gap-3">
              <Sparkles className="mt-0.5 size-4 shrink-0 text-amber-300" />
              <p>
                <span className="font-medium">什么场景：</span>
                <span className="text-primary-foreground/70">什么时候发生，有多麻烦？</span>
              </p>
            </div>
            <div className="flex gap-3">
              <CheckCircle2 className="mt-0.5 size-4 shrink-0 text-amber-300" />
              <p>
                <span className="font-medium">想要什么：</span>
                <span className="text-primary-foreground/70">理想结果是什么？方案可选。</span>
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    </AppLayout>
  );
}
