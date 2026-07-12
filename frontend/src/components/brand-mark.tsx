import { Lightbulb } from "lucide-react";
import { cn } from "@/lib/utils";

export function BrandMark({ className }: { className?: string }) {
  return (
    <span
      className={cn(
        "inline-flex size-9 items-center justify-center rounded-xl bg-reward-soft",
        "text-amber-700 shadow-sm ring-1 ring-amber-200/70",
        className,
      )}
      aria-hidden="true"
    >
      <Lightbulb className="size-5" strokeWidth={2.2} />
    </span>
  );
}
