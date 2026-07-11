export type UserRole = "user" | "admin";
export type UserStatus = "active" | "disabled";

export interface User {
  id: number;
  username: string;
  role: UserRole;
  status: UserStatus;
  created_at: string;
}

export interface Credentials {
  username: string;
  password: string;
}

export class ApiError extends Error {
  status: number;
  detail?: string;

  constructor(message: string, status: number, detail?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}
