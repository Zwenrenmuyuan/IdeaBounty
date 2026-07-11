import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
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
      <div className="mb-4">
        <Link
          to="/ideas"
          className="text-sm text-muted-foreground transition-colors hover:text-foreground"
        >
          ← 返回列表
        </Link>
      </div>

      <Card>
        <CardHeader>
          <CardTitle>提交点子</CardTitle>
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
              {submitting ? "提交中..." : "提交点子"}
            </Button>
            <Button variant="outline" asChild>
              <Link to="/ideas">取消</Link>
            </Button>
          </CardFooter>
        </form>
      </Card>
    </AppLayout>
  );
}
