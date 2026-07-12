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

/* ── 点子领域类型 ────────────────────────────────────────── */

export type IdeaProcessingStatus =
  | "pending"
  | "evaluating"
  | "embedding"
  | "checking_duplicate"
  | "completed"
  | "failed";

export type InputDecision = "accept" | "clarify" | "reject";
export type DuplicateVerdict = "duplicate" | "related" | "novel";
export type AdminAction = "confirmed" | "adjusted" | "rejected";

export type PayoutStatus =
  | "not_ready"
  | "awaiting_admin"
  | "confirmed"
  | "not_applicable";

export type ScoreConfidence = "high" | "medium" | "low";

export interface IdeaCreateRequest {
  submission_key: string;
  raw_content: string;
}

export interface IdeaSupplementRequest {
  raw_content: string;
}

export interface DimensionScore {
  score: number;
  reason: string;
  confidence: ScoreConfidence;
  evidence_fields: string[];
}

export interface EvaluationScores {
  demand_breadth: DimensionScore;
  pain_intensity: DimensionScore;
  willingness_to_pay: DimensionScore;
  feasibility: DimensionScore;
  novelty: DimensionScore;
}

export interface IdeaDuplicateResult {
  verdict: DuplicateVerdict;
  matched_public_id: string | null;
  matched_idea_url: string | null;
  same_aspects: string[];
  different_aspects: string[];
  reason: string;
}

export interface SimulatedPayout {
  amount: number;
  reference: string;
  confirmed_at: string;
}

export interface IdeaSummary {
  public_id: string;
  submission_key: string;
  raw_content: string;
  generated_title: string | null;
  processing_status: IdeaProcessingStatus;
  input_decision: InputDecision | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
}

export interface IdeaResponse extends IdeaSummary {
  decision_reason: string | null;
  clarification_question: string | null;
  evaluation: EvaluationScores | null;
  duplicate_result: IdeaDuplicateResult | null;
  commercial_score: number | null;
  base_amount: number | null;
  duplicate_deduction: number | null;
  final_amount: number | null;
  admin_action: AdminAction | null;
  admin_reason: string | null;
  payout_status: PayoutStatus;
  payout: SimulatedPayout | null;
}

export interface IdeaListResponse {
  items: IdeaSummary[];
  total: number;
  limit: number;
  offset: number;
}

export interface PublicIdeaSummary {
  public_id: string;
  generated_title: string | null;
  target_audience: string | null;
  pain_point: string | null;
  context: string | null;
  solution_present: boolean;
  solution_outline: string | null;
  created_date: string;
}

/* ── 管理后台类型 ────────────────────────────────────────── */

export interface AdminSummary {
  total_submissions: number;
  completed_accepts: number;
  duplicate_count: number;
  estimated_total: number;
  confirmed_payout_count: number;
  simulated_payout_total: number;
}

export interface AdminIdeaListItem {
  public_id: string;
  username: string;
  generated_title: string | null;
  processing_status: IdeaProcessingStatus;
  input_decision: InputDecision | null;
  commercial_score: number | null;
  final_amount: number | null;
  duplicate_verdict: DuplicateVerdict | null;
  admin_action: AdminAction | null;
  created_at: string;
}

export interface AdminIdeaListResponse {
  items: AdminIdeaListItem[];
  total: number;
  limit: number;
  offset: number;
}

export interface AdminIdeaDetailResponse {
  username: string;
  idea: IdeaResponse;
  admin_reason: string | null;
  admin_processed_at: string | null;
}

export type AdminIdeaProcessRequest =
  | { action: "confirmed" }
  | { action: "adjusted"; amount: number; reason: string }
  | { action: "rejected"; reason: string };
