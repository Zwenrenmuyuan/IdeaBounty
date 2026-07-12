import { useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { FileText, LayoutDashboard, LogOut, Plus } from "lucide-react";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import { BrandMark } from "@/components/brand-mark";
import { ApiError } from "@/types";
import { cn } from "@/lib/utils";

const NAV_LINK_CLASS = [
  "inline-flex h-9 items-center gap-1.5 rounded-lg px-2.5 text-sm font-medium",
  "transition-colors sm:px-3",
].join(" ");

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
    <div className="min-h-screen">
      <header className="sticky top-0 z-20 border-b border-border/70 bg-background/85 backdrop-blur-xl">
        <div className="mx-auto flex min-h-16 max-w-5xl flex-wrap items-center justify-between gap-2 px-4 py-2">
          <NavLink
            to="/ideas"
            className="flex items-center gap-2.5"
            aria-label="Idea Bounty 首页"
          >
            <BrandMark />
            <span className="hidden text-base font-semibold tracking-tight min-[390px]:inline">
              Idea Bounty
            </span>
          </NavLink>
          <nav className="flex min-w-0 items-center gap-0.5 sm:gap-1" aria-label="主导航">
            <NavLink
              to="/ideas"
              className={({ isActive }) =>
                cn(
                  NAV_LINK_CLASS,
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-white/60 hover:text-foreground",
                )
              }
            >
              <FileText />
              <span className="hidden sm:inline">我的投稿</span>
            </NavLink>
            <NavLink
              to="/ideas/new"
              className={({ isActive }) =>
                cn(
                  NAV_LINK_CLASS,
                  isActive
                    ? "bg-primary/10 text-primary"
                    : "text-muted-foreground hover:bg-white/60 hover:text-foreground",
                )
              }
            >
              <Plus />
              <span className="hidden sm:inline">提交点子</span>
            </NavLink>
            {user?.role === "admin" && (
              <NavLink
                to="/admin"
                className={({ isActive }) =>
                  cn(
                    NAV_LINK_CLASS,
                    isActive
                      ? "bg-primary/10 text-primary"
                      : "text-muted-foreground hover:bg-white/60 hover:text-foreground",
                  )
                }
              >
                <LayoutDashboard />
                <span className="hidden sm:inline">管理后台</span>
              </NavLink>
            )}
            <div className="ml-1 flex items-center gap-2 border-l pl-2 sm:ml-2 sm:pl-3">
              <span className="hidden max-w-24 truncate text-sm text-muted-foreground md:inline">
                {user?.username}
              </span>
              <Button
                variant="outline"
                size="icon"
                onClick={handleLogout}
                disabled={loggingOut}
                aria-label={loggingOut ? "退出中" : "退出登录"}
                title="退出登录"
              >
                <LogOut />
              </Button>
            </div>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-5xl px-4 py-7 sm:py-10">
        {logoutError && (
          <div
            role="alert"
            className="mb-5 rounded-xl border border-destructive/15 bg-destructive/10 px-4 py-3 text-sm text-destructive"
          >
            {logoutError}
          </div>
        )}
        {children}
      </main>
    </div>
  );
}
