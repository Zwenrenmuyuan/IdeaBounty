import { Badge } from "@/components/ui/badge";
import type {
  AdminAction,
  IdeaProcessingStatus,
  InputDecision,
  PayoutStatus,
} from "@/types";
import {
  adminActionLabel,
  inputDecisionLabel,
  payoutStatusLabel,
  statusLabel,
} from "@/lib/idea-display";
import type { BadgeProps } from "@/components/ui/badge";

type BadgeVariant = NonNullable<BadgeProps["variant"]>;

const STATUS_VARIANTS: Record<IdeaProcessingStatus, BadgeVariant> = {
  pending: "secondary",
  evaluating: "secondary",
  embedding: "secondary",
  checking_duplicate: "secondary",
  completed: "success",
  failed: "destructive",
};

export function IdeaStatusBadge({
  status,
}: {
  status: IdeaProcessingStatus;
}) {
  return (
    <Badge variant={STATUS_VARIANTS[status] ?? "default"}>
      {statusLabel(status)}
    </Badge>
  );
}

export function InputDecisionBadge({
  decision,
}: {
  decision: InputDecision | null;
}) {
  if (decision === null) return null;
  const variant: BadgeVariant =
    decision === "accept"
      ? "success"
      : decision === "reject"
        ? "destructive"
        : "warning";
  return (
    <Badge variant={variant}>{inputDecisionLabel(decision)}</Badge>
  );
}

export function AdminActionBadge({
  action,
}: {
  action: AdminAction | null;
}) {
  if (action === null) return null;
  return <Badge variant="outline">{adminActionLabel(action)}</Badge>;
}

export function PayoutStatusBadge({
  status,
}: {
  status: PayoutStatus;
}) {
  const variant: BadgeVariant =
    status === "confirmed"
      ? "success"
      : status === "not_applicable"
        ? "secondary"
        : "warning";
  return (
    <Badge variant={variant}>{payoutStatusLabel(status)}</Badge>
  );
}
