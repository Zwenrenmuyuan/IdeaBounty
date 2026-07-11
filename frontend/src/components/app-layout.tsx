import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { ApiError } from "@/types";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);
  const [logoutError, setLogoutError] = useState<string | null>(null);

  async function handleLogout() {
    setLoggingOut(true);
    setLogoutError(null);
    try {
      await logout();
      navigate("/login", { replace: true });
    } catch (error) {
      setLogoutError(
        error instanceof ApiError ? error.message : "退出失败，请稍后重试",
      );
    } finally {
      setLoggingOut(false);
    }
  }

  return (
    <div className="min-h-screen bg-background">
      <header className="sticky top-0 z-10 border-b bg-background/95 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-4xl items-center justify-between px-4">
          <Link to="/ideas" className="text-lg font-semibold">
            Idea Bounty
          </Link>
          <nav className="flex items-center gap-2 sm:gap-4">
            <Link
              to="/ideas"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              我的投稿
            </Link>
            <Link
              to="/ideas/new"
              className="text-sm text-muted-foreground transition-colors hover:text-foreground"
            >
              提交点子
            </Link>
            {user?.role === "admin" && (
              <span className="text-sm text-muted-foreground">管理后台</span>
            )}
            <div className="flex items-center gap-2">
              <span className="text-sm text-muted-foreground hidden sm:inline">
                {user?.username}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={handleLogout}
                disabled={loggingOut}
              >
                {loggingOut ? "退出中..." : "退出登录"}
              </Button>
            </div>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">
        {logoutError && (
          <div
            role="alert"
            className="mb-4 rounded-md bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {logoutError}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
