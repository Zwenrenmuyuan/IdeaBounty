import { Routes, Route, Navigate } from "react-router-dom";
import { LoginPage } from "@/pages/login";
import { RegisterPage } from "@/pages/register";
import { IdeaListPage } from "@/pages/idea-list";
import { IdeaCreatePage } from "@/pages/idea-create";
import { IdeaDetailPage } from "@/pages/idea-detail";
import { IdeaSummaryPage } from "@/pages/idea-summary";
import { ProtectedRoute } from "@/components/protected-route";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route
        path="/ideas"
        element={
          <ProtectedRoute>
            <IdeaListPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ideas/new"
        element={
          <ProtectedRoute>
            <IdeaCreatePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/ideas/:publicId"
        element={
          <ProtectedRoute>
            <IdeaDetailPage />
          </ProtectedRoute>
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
      <Route path="/" element={<Navigate to="/ideas" replace />} />
      <Route path="*" element={<Navigate to="/ideas" replace />} />
    </Routes>
  );
}
