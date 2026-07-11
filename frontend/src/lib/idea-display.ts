import type {
  AdminAction,
  DuplicateVerdict,
  IdeaProcessingStatus,
  InputDecision,
  PayoutStatus,
  ScoreConfidence,
} from "@/types";

const STATUS_LABELS: Record<IdeaProcessingStatus, string> = {
  pending: "待处理",
  evaluating: "AI 评估中",
  embedding: "生成语义向量",
  checking_duplicate: "查重中",
  completed: "已完成",
  failed: "处理失败",
};

const INPUT_DECISION_LABELS: Record<InputDecision, string> = {
  accept: "已接受",
  clarify: "需补充信息",
  reject: "已拒绝",
};

const DUPLICATE_VERDICT_LABELS: Record<DuplicateVerdict, string> = {
  duplicate: "高度重复",
  related: "存在相关性",
  novel: "全新痛点",
};

const ADMIN_ACTION_LABELS: Record<AdminAction, string> = {
  confirmed: "已确认",
  adjusted: "已调整",
  rejected: "已驳回",
};

const PAYOUT_STATUS_LABELS: Record<PayoutStatus, string> = {
  not_ready: "投稿尚未完成处理",
  awaiting_admin: "等待管理员最终处理",
  confirmed: "模拟打款已确认",
  not_applicable: "无需模拟打款",
};

const CONFIDENCE_LABELS: Record<ScoreConfidence, string> = {
  high: "高",
  medium: "中",
  low: "低",
};

const DIMENSION_LABELS: Record<string, string> = {
  demand_breadth: "需求广度",
  pain_intensity: "痛点强度",
  willingness_to_pay: "付费意愿",
  feasibility: "可行性",
  novelty: "新颖性",
};

const FIELD_LABELS: Record<string, string> = {
  target_audience: "目标用户",
  pain_point: "痛点",
  context: "场景背景",
  frequency_or_severity: "频率或严重程度",
  current_alternative: "现有替代方案",
  desired_outcome: "期望结果",
  proposed_solution: "提出方案",
  solution_mechanism: "方案机制",
  value_proposition: "价值主张",
};

export function statusLabel(status: IdeaProcessingStatus): string {
  return STATUS_LABELS[status] ?? status;
}

export function inputDecisionLabel(
  decision: InputDecision | null,
): string | null {
  if (decision === null) return null;
  return INPUT_DECISION_LABELS[decision] ?? decision;
}

export function duplicateVerdictLabel(verdict: DuplicateVerdict): string {
  return DUPLICATE_VERDICT_LABELS[verdict] ?? verdict;
}

export function adminActionLabel(
  action: AdminAction | null,
): string | null {
  if (action === null) return null;
  return ADMIN_ACTION_LABELS[action] ?? action;
}

export function payoutStatusLabel(status: PayoutStatus): string {
  return PAYOUT_STATUS_LABELS[status] ?? status;
}

export function confidenceLabel(confidence: ScoreConfidence): string {
  return CONFIDENCE_LABELS[confidence] ?? confidence;
}

export function dimensionLabel(key: string): string {
  return DIMENSION_LABELS[key] ?? key;
}

export function fieldLabel(key: string): string {
  return FIELD_LABELS[key] ?? key;
}

export function formatAmount(amount: number | null): string {
  if (amount === null || Number.isNaN(amount)) return "尚未生成";
  return `¥${amount.toFixed(2)}`;
}

export function formatDateTime(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function formatDate(iso: string): string {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return date.toLocaleDateString("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export function truncateContent(content: string, maxLen = 50): string {
  if (content.length <= maxLen) return content;
  return `${content.slice(0, maxLen)}…`;
}
