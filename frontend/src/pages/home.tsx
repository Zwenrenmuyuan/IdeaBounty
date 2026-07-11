import { useAuth } from "@/hooks/use-auth";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";

export function HomePage() {
  const { user, logout } = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-4">
      <Card className="w-full max-w-md">
        <CardHeader className="space-y-1">
          <CardTitle className="text-2xl">欢迎，{user?.username}</CardTitle>
          <CardDescription>
            你已登录 Idea Bounty。点子提交功能即将上线。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <dl className="space-y-2 text-sm">
            <div className="flex justify-between">
              <dt className="text-muted-foreground">角色</dt>
              <dd>{user?.role === "admin" ? "管理员" : "普通用户"}</dd>
            </div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">注册时间</dt>
              <dd>{new Date(user?.created_at ?? "").toLocaleDateString("zh-CN")}</dd>
            </div>
          </dl>
          <Button variant="outline" className="w-full" onClick={() => logout()}>
            退出登录
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
