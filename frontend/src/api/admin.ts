import { apiClient } from "@/api/client";
import type {
  AdminIdeaDetailResponse,
  AdminIdeaListResponse,
  AdminIdeaProcessRequest,
  AdminSummary,
} from "@/types";

export const ADMIN_PAGE_SIZE = 20;

export function getAdminSummary(signal?: AbortSignal): Promise<AdminSummary> {
  return apiClient.get<AdminSummary>("/admin/summary", signal);
}

export function listAdminIdeas(
  offset = 0,
  limit = ADMIN_PAGE_SIZE,
  signal?: AbortSignal,
): Promise<AdminIdeaListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiClient.get<AdminIdeaListResponse>(
    `/admin/ideas?${params.toString()}`,
    signal,
  );
}

export function getAdminIdea(
  publicId: string,
  signal?: AbortSignal,
): Promise<AdminIdeaDetailResponse> {
  return apiClient.get<AdminIdeaDetailResponse>(
    `/admin/ideas/${publicId}`,
    signal,
  );
}

export function processAdminIdea(
  publicId: string,
  payload: AdminIdeaProcessRequest,
  signal?: AbortSignal,
): Promise<AdminIdeaDetailResponse> {
  return apiClient.post<AdminIdeaDetailResponse>(
    `/admin/ideas/${publicId}/process`,
    payload,
    signal,
  );
}
