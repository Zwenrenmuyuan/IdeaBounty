import { apiClient } from "@/api/client";
import type {
  IdeaCreateRequest,
  IdeaListResponse,
  IdeaResponse,
  IdeaSupplementRequest,
  PublicIdeaSummary,
} from "@/types";

const PAGE_SIZE = 20;

export function createIdea(
  payload: IdeaCreateRequest,
  signal?: AbortSignal,
): Promise<IdeaResponse> {
  return apiClient.post<IdeaResponse>("/me/ideas", payload, signal);
}

export function listIdeas(
  offset = 0,
  limit = PAGE_SIZE,
  signal?: AbortSignal,
): Promise<IdeaListResponse> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  });
  return apiClient.get<IdeaListResponse>(
    `/me/ideas?${params.toString()}`,
    signal,
  );
}

export function getIdea(
  publicId: string,
  signal?: AbortSignal,
): Promise<IdeaResponse> {
  return apiClient.get<IdeaResponse>(`/me/ideas/${publicId}`, signal);
}

export function retryIdea(
  publicId: string,
  signal?: AbortSignal,
): Promise<IdeaResponse> {
  return apiClient.post<IdeaResponse>(
    `/me/ideas/${publicId}/retry`,
    undefined,
    signal,
  );
}

export function supplementIdea(
  publicId: string,
  payload: IdeaSupplementRequest,
  signal?: AbortSignal,
): Promise<IdeaResponse> {
  return apiClient.post<IdeaResponse>(
    `/me/ideas/${publicId}/supplement`,
    payload,
    signal,
  );
}

export function deleteIdea(
  publicId: string,
  signal?: AbortSignal,
): Promise<void> {
  return apiClient.delete<void>(`/me/ideas/${publicId}`, signal);
}

export function getPublicSummary(
  publicId: string,
  signal?: AbortSignal,
): Promise<PublicIdeaSummary> {
  return apiClient.get<PublicIdeaSummary>(
    `/ideas/${publicId}/summary`,
    signal,
  );
}

export { PAGE_SIZE };
