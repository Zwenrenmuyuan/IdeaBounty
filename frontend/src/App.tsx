import { Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";
import { IdeaListPage } from "@/pages/idea-list";
import { IdeaCreatePage } from "@/pages/idea-create";
import { IdeaDetailPage } from "@/pages/idea-detail";
import { IdeaSummaryPage } from "@/pages/idea-summary";
import { ProtectedRoute } from "@/components/protected-route";
import { SubmitterRoute } from "@/components/submitter-route";
import { AdminRoute } from "@/components/admin-route";
import { AdminIdeaListPage } from "@/pages/admin-idea-list";
import { AdminIdeaDetailPage } from "@/pages/admin-idea-detail";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/ideas"
        element={
          <SubmitterRoute>
            <IdeaListPage />
          </SubmitterRoute>
        }
      />
      <Route
        path="/ideas/new"
        element={
          <SubmitterRoute>
            <IdeaCreatePage />
          </SubmitterRoute>
        }
      />
      <Route
        path="/ideas/:publicId"
        element={
          <SubmitterRoute>
            <IdeaDetailPage />
          </SubmitterRoute>
        }
      />
      <Route
        path="/ideas/:publicId/summary"
        element={
          <ProtectedRoute>
            <IdeaSummaryPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/admin"
        element={
          <AdminRoute>
            <AdminIdeaListPage />
          </AdminRoute>
        }
      />
      <Route
        path="/admin/ideas/:publicId"
        element={
          <AdminRoute>
            <AdminIdeaDetailPage />
          </AdminRoute>
        }
      />
      <Route path="/" element={<Navigate to="/ideas" replace />} />
      <Route path="*" element={<Navigate to="/ideas" replace />} />
    </Routes>
  );
}
