import { CheckCircle2, CircleDashed, Clock3, TriangleAlert } from "lucide-react";

import { cn } from "@/lib/utils";
import type { ConfidenceLevel, InvestigationStatus, StepStatus } from "@/lib/investigations";

const statusStyles = {
  queued: "border-sky-400/20 bg-sky-400/[0.08] text-sky-300",
  pending: "border-white/10 bg-white/[0.04] text-[#8c8ca8]",
  running: "border-violet-400/25 bg-violet-400/[0.09] text-violet-300",
  completed: "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
  failed: "border-red-400/20 bg-red-400/[0.08] text-red-300",
  skipped: "border-amber-400/20 bg-amber-400/[0.08] text-amber-300",
};

export function StatusBadge({ status }: { status: InvestigationStatus | StepStatus }) {
  const Icon =
    status === "completed"
      ? CheckCircle2
      : status === "failed"
        ? TriangleAlert
        : status === "running"
          ? CircleDashed
          : Clock3;

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em]",
        statusStyles[status],
      )}
    >
      <Icon className={cn("h-3 w-3", status === "running" && "animate-spin")} />
      {status}
    </span>
  );
}

const confidenceStyles: Record<ConfidenceLevel, string> = {
  high: "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
  medium: "border-amber-400/20 bg-amber-400/[0.08] text-amber-300",
  low: "border-rose-400/20 bg-rose-400/[0.08] text-rose-300",
};

export function ConfidenceIndicator({
  score,
  level,
  compact = false,
}: {
  score: number;
  level: ConfidenceLevel;
  compact?: boolean;
}) {
  return (
    <div
      className={cn(
        "inline-flex items-center gap-2 rounded-full border font-semibold",
        confidenceStyles[level],
        compact ? "px-2.5 py-1 text-[10px]" : "px-3 py-1.5 text-xs",
      )}
    >
      <span className="h-1.5 w-1.5 rounded-full bg-current" />
      {Math.round(score * 100)}% {level} confidence
    </div>
  );
}
