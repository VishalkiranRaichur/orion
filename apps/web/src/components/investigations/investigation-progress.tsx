import { Check, Circle, LoaderCircle, Minus, TriangleAlert } from "lucide-react";

import type { InvestigationDetail, InvestigationStep } from "@/lib/investigations";
import { formatDuration, toolLabels } from "@/lib/investigations";
import { cn } from "@/lib/utils";

function StepIcon({ step }: { step: InvestigationStep }) {
  if (step.status === "completed") return <Check className="h-3.5 w-3.5" />;
  if (step.status === "running") return <LoaderCircle className="h-3.5 w-3.5 animate-spin" />;
  if (step.status === "failed") return <TriangleAlert className="h-3.5 w-3.5" />;
  if (step.status === "skipped") return <Minus className="h-3.5 w-3.5" />;
  return <Circle className="h-3 w-3" />;
}

export function InvestigationProgress({ investigation }: { investigation: InvestigationDetail }) {
  const resolved = investigation.steps.filter((step) =>
    ["completed", "failed", "skipped"].includes(step.status),
  ).length;
  const total = investigation.steps.length;

  return (
    <section className="rounded-2xl border border-white/[0.07] bg-[#0f0f14] p-5">
      <div className="mb-5 flex items-start justify-between gap-4">
        <div>
          <h2 className="text-sm font-semibold text-white">Investigation progress</h2>
          <p className="mt-1 text-xs text-[#8c8ca8]">
            {total ? `${resolved} of ${total} steps resolved` : "ORION is creating a bounded plan."}
          </p>
        </div>
        {total > 0 && <span className="text-xs font-semibold text-[#8f8fff]">{Math.round((resolved / total) * 100)}%</span>}
      </div>

      {total > 0 && (
        <div className="mb-5 h-1 overflow-hidden rounded-full bg-white/[0.05]">
          <div
            className="h-full rounded-full bg-[#7c7cf8] transition-[width] duration-500"
            style={{ width: `${(resolved / total) * 100}%` }}
          />
        </div>
      )}

      {total === 0 ? (
        <div className="flex items-center gap-3 rounded-xl border border-[#7c7cf8]/15 bg-[#7c7cf8]/[0.05] px-4 py-4">
          <LoaderCircle className="h-4 w-4 animate-spin text-[#8f8fff]" />
          <div>
            <p className="text-xs font-medium text-white">
              {investigation.status === "queued" ? "Waiting for an investigation worker" : "Planning the investigation"}
            </p>
            <p className="mt-1 text-[11px] text-[#8c8ca8]">No progress is estimated until the persisted plan is available.</p>
          </div>
        </div>
      ) : (
        <ol className="space-y-1">
          {investigation.steps.map((step, index) => {
            const duration = formatDuration(step.started_at, step.completed_at);
            return (
              <li key={step.sequence} className="relative flex gap-3 pb-4 last:pb-0">
                {index < investigation.steps.length - 1 && (
                  <div className="absolute left-[13px] top-7 h-[calc(100%-20px)] w-px bg-white/[0.07]" />
                )}
                <div
                  className={cn(
                    "relative z-10 flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-full border",
                    step.status === "completed" && "border-emerald-400/20 bg-emerald-400/[0.08] text-emerald-300",
                    step.status === "running" && "border-[#7c7cf8]/30 bg-[#7c7cf8]/10 text-[#8f8fff]",
                    step.status === "failed" && "border-red-400/20 bg-red-400/[0.08] text-red-300",
                    step.status === "skipped" && "border-amber-400/20 bg-amber-400/[0.08] text-amber-300",
                    step.status === "pending" && "border-white/[0.08] bg-[#111116] text-[#8c8ca8]/50",
                  )}
                >
                  <StepIcon step={step} />
                </div>
                <div className="min-w-0 flex-1 pt-1">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-xs font-medium text-[#e8e8ed]">{step.description}</p>
                      <p className="mt-1 text-[10px] text-[#8c8ca8]/55">
                        {toolLabels[step.tool] ?? step.tool.replaceAll("_", " ")}
                        {!step.required && " · optional"}
                      </p>
                    </div>
                    {duration && <span className="text-[10px] text-[#8c8ca8]/45">{duration}</span>}
                  </div>
                  {step.error && <p className="mt-2 text-[11px] leading-5 text-red-300/80">{step.error}</p>}
                </div>
              </li>
            );
          })}
        </ol>
      )}
    </section>
  );
}
