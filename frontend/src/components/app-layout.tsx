import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { user, logout } = useAuth();
  const navigate = useNavigate();

  async function handleLogout() {
    await logout();
    navigate("/login", { replace: true });
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
              >
                退出登录
              </Button>
            </div>
          </nav>
        </div>
      </header>
      <main className="mx-auto max-w-4xl px-4 py-6">{children}</main>
    </div>
  );
}
