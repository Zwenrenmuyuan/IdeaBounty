import { apiClient } from "@/api/client";
import type { User, Credentials } from "@/types";

export function register(credentials: Credentials): Promise<User> {
  return apiClient.post<User>("/auth/register", credentials);
}

export function login(credentials: Credentials): Promise<User> {
  return apiClient.post<User>("/auth/login", credentials);
}

export function getCurrentUser(signal?: AbortSignal): Promise<User> {
  return apiClient.get<User>("/auth/me", signal);
}

export function logout(): Promise<void> {
  return apiClient.post<void>("/auth/logout");
}
