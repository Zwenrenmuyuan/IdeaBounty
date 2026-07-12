import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "@/hooks/use-auth";

export function AdminRoute({ children }: { children: React.ReactNode }) {
  const { user, loading } = useAuth();
  const location = useLocation();

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center">
        <p className="text-muted-foreground">加载中...</p>
      </div>
    );
  }

  if (!user) {
    return <Navigate to="/login" state={{ from: location.pathname }} replace />;
  }

  if (user.role !== "admin") {
    return <Navigate to="/ideas" replace />;
  }

  return <>{children}</>;
}
