import { cn } from "@/lib/utils";

export function ScoreMeter({
  score,
  className,
}: {
  score: number;
  className?: string;
}) {
  return (
    <div
      className={cn("h-1.5 overflow-hidden rounded-full bg-secondary", className)}
      role="meter"
      aria-valuemin={0}
      aria-valuemax={5}
      aria-valuenow={score}
    >
      <div
        className={
          "h-full rounded-full bg-gradient-to-r from-amber-400 to-amber-500 " +
          "transition-[width]"
        }
        style={{ width: `${(score / 5) * 100}%` }}
      />
    </div>
  );
}
