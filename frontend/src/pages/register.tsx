import { useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";
import { ApiError } from "@/types";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

const USERNAME_PATTERN = /^[a-z0-9_]{3,32}$/;

export function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuth();

  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [submitting, setSubmitting] = useState(false);

  function validate(): boolean {
    const errors: Record<string, string> = {};

    const trimmedUsername = username.trim().toLowerCase();
    if (!trimmedUsername) {
      errors.username = "请输入用户名";
    } else if (!USERNAME_PATTERN.test(trimmedUsername)) {
      errors.username = "用户名只能包含小写字母、数字和下划线，3-32 个字符";
    }

    if (!password) {
      errors.password = "请输入密码";
    } else if (password.length < 8) {
      errors.password = "密码至少 8 个字符";
    } else if (password.length > 128) {
      errors.password = "密码不能超过 128 个字符";
    }

    if (confirmPassword !== password) {
      errors.confirmPassword = "两次输入的密码不一致";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!validate()) return;

    setSubmitting(true);
    setError(null);
    try {
      await register({ username: username.trim(), password });
      navigate("/");
    } catch (err) {
      if (err instanceof ApiError && err.status === 409) {
        setError("用户名已存在");
      } else if (err instanceof ApiError) {
        setError(err.message);
      } else {
        setError("注册失败，请稍后重试");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">注册账号</CardTitle>
          <CardDescription>
            注册后即可提交点子并获取 AI 评估的红包
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
              <Label htmlFor="username">用户名</Label>
              <Input
                id="username"
                type="text"
                autoComplete="username"
                placeholder="3-32 位小写字母、数字或下划线"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                aria-invalid={!!fieldErrors.username}
                aria-describedby={fieldErrors.username ? "username-error" : undefined}
              />
              {fieldErrors.username && (
                <p id="username-error" className="text-sm text-destructive">
                  {fieldErrors.username}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="password">密码</Label>
              <Input
                id="password"
                type="password"
                autoComplete="new-password"
                placeholder="至少 8 个字符"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                aria-invalid={!!fieldErrors.password}
                aria-describedby={fieldErrors.password ? "password-error" : undefined}
              />
              {fieldErrors.password && (
                <p id="password-error" className="text-sm text-destructive">
                  {fieldErrors.password}
                </p>
              )}
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm-password">确认密码</Label>
              <Input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                placeholder="再次输入密码"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                aria-invalid={!!fieldErrors.confirmPassword}
                aria-describedby={fieldErrors.confirmPassword ? "confirm-password-error" : undefined}
              />
              {fieldErrors.confirmPassword && (
                <p id="confirm-password-error" className="text-sm text-destructive">
                  {fieldErrors.confirmPassword}
                </p>
              )}
            </div>
          </CardContent>
          <CardFooter className="flex flex-col gap-4">
            <Button type="submit" className="w-full" disabled={submitting}>
              {submitting ? "注册中..." : "注册"}
            </Button>
            <p className="text-sm text-muted-foreground">
              已有账号？{" "}
              <Link to="/login" className="text-primary underline-offset-4 hover:underline">
                去登录
              </Link>
            </p>
          </CardFooter>
        </form>
      </Card>
    </div>
  );
}
