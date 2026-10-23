"use client";

import { AlertTriangle, ArrowLeft, LoaderCircle, RefreshCw, RotateCcw } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { InvestigationProgress } from "@/components/investigations/investigation-progress";
import { InvestigationResults } from "@/components/investigations/investigation-results";
import { ConfidenceIndicator, StatusBadge } from "@/components/investigations/status";
import { ApiError } from "@/lib/api";
import {
  createInvestigation,
  failureMessage,
  formatDateTime,
} from "@/lib/investigations";
import { useInvestigation } from "@/lib/use-investigation";

export default function InvestigationDetailPage() {
  const params = useParams<{ investigationId: string }>();
  const router = useRouter();
  const id = params.investigationId;
  const { investigation, loading, error, retryNow } = useInvestigation(id);
  const [rerunning, setRerunning] = useState(false);
  const [rerunError, setRerunError] = useState("");

  async function runAgain() {
    if (!investigation || rerunning) return;
    try {
      setRerunning(true);
      setRerunError("");
      const created = await createInvestigation(investigation.question);
      router.push(`/dashboard/investigate/${created.id}`);
    } catch (caught) {
      setRerunError(caught instanceof Error ? caught.message : "Could not create a new investigation.");
      setRerunning(false);
    }
  }

  if (loading && !investigation) return <DetailSkeleton />;

  if (!investigation && error instanceof ApiError && error.status === 404) {
    return (
      <DetailState
        title="Investigation not found"
        text="This investigation does not exist or is not available in the current workspace."
        action={<Link href="/dashboard/investigate" className="text-xs font-semibold text-[#8f8fff]">Return to Investigate</Link>}
      />
    );
  }

  if (!investigation) {
    return (
      <DetailState
        title="Could not load investigation"
        text={error?.message ?? "The ORION API could not be reached."}
        action={<button type="button" onClick={retryNow} className="inline-flex items-center gap-2 text-xs font-semibold text-[#8f8fff]"><RefreshCw className="h-3.5 w-3.5" /> Retry now</button>}
      />
    );
  }

  const brief = investigation.executive_brief;
  const terminal = investigation.status === "completed" || investigation.status === "failed";

  return (
    <div className="min-h-screen bg-[#09090d] px-4 py-6 text-white sm:px-7 sm:py-8 lg:px-10">
      <div className="mx-auto max-w-7xl">
        <Link href="/dashboard/investigate" className="mb-6 inline-flex items-center gap-2 text-xs text-[#8c8ca8] transition hover:text-white">
          <ArrowLeft className="h-3.5 w-3.5" /> All investigations
        </Link>

        {error && (
          <div className="mb-5 flex items-center justify-between gap-4 rounded-xl border border-amber-400/20 bg-amber-400/[0.06] px-4 py-3 text-xs text-amber-100">
            <span>Connection interrupted. Showing the last known investigation state.</span>
            <button type="button" onClick={retryNow} className="flex-shrink-0 font-semibold">Retry now</button>
          </div>
        )}

        <header className="mb-7 border-b border-white/[0.06] pb-7">
          <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
            <div className="max-w-4xl">
              <div className="flex flex-wrap items-center gap-2">
                <StatusBadge status={investigation.status} />
                <span className="text-[10px] uppercase tracking-[0.1em] text-[#8c8ca8]/45">Created {formatDateTime(investigation.created_at)}</span>
              </div>
              <h1 className="mt-4 text-xl font-semibold leading-8 tracking-[-0.02em] text-white sm:text-2xl">{investigation.question}</h1>
              {investigation.assumptions.length > 0 && (
                <p className="mt-3 text-xs leading-5 text-[#8c8ca8]">Assumption: {investigation.assumptions.join(" ")}</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              {brief && <ConfidenceIndicator score={brief.confidence.score} level={brief.confidence.level} />}
              {terminal && (
                <button
                  type="button"
                  onClick={() => void runAgain()}
                  disabled={rerunning}
                  className="inline-flex items-center gap-2 rounded-lg border border-white/[0.09] bg-white/[0.025] px-3.5 py-2 text-xs font-medium text-[#c7c7d1] transition hover:border-white/[0.16] hover:text-white disabled:opacity-50"
                >
                  {rerunning ? <LoaderCircle className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />}
                  {rerunning ? "Creating…" : "Run again"}
                </button>
              )}
            </div>
          </div>
          {rerunError && <p className="mt-4 text-xs text-red-300">{rerunError}</p>}
        </header>

        {investigation.status === "failed" && (
          <FailurePanel
            message={failureMessage(investigation.failure_code, investigation.error)}
            code={investigation.failure_code}
            technical={investigation.error}
          />
        )}

        <div className="grid items-start gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
          <div className="min-w-0">
            {terminal &&
            (investigation.executive_brief ||
              investigation.claims.length > 0 ||
              investigation.evidence.length > 0 ||
              investigation.steps.length > 0) ? (
              <InvestigationResults investigation={investigation} />
            ) : investigation.status === "failed" ? (
              <div className="rounded-2xl border border-dashed border-white/[0.08] bg-[#0f0f14] px-6 py-16 text-center">
                <AlertTriangle className="mx-auto h-6 w-6 text-red-300/70" />
                <h2 className="mt-5 text-sm font-medium text-white">No validated result available</h2>
                <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-[#8c8ca8]">Review the failure and tool activity, then run the question again when the underlying issue is resolved.</p>
              </div>
            ) : (
              <div className="rounded-2xl border border-white/[0.07] bg-[#0f0f14] px-6 py-16 text-center">
                <LoaderCircle className="mx-auto h-6 w-6 animate-spin text-[#8f8fff]" />
                <h2 className="mt-5 text-sm font-medium text-white">ORION is investigating</h2>
                <p className="mx-auto mt-2 max-w-md text-xs leading-5 text-[#8c8ca8]">The Executive Brief will appear here after claims and evidence have been validated.</p>
              </div>
            )}
          </div>
          <div className="xl:sticky xl:top-6">
            <InvestigationProgress investigation={investigation} />
          </div>
        </div>
      </div>
    </div>
  );
}

function FailurePanel({ message, code, technical }: { message: string; code: string | null; technical: string | null }) {
  return (
    <section className="mb-5 rounded-2xl border border-red-400/20 bg-red-400/[0.055] p-5">
      <div className="flex items-start gap-3">
        <div className="flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-lg bg-red-400/10"><AlertTriangle className="h-4 w-4 text-red-300" /></div>
        <div className="min-w-0">
          <h2 className="text-sm font-semibold text-red-100">Investigation could not complete</h2>
          <p className="mt-2 text-xs leading-5 text-red-200/80">{message}</p>
          {(code || technical) && (
            <details className="mt-3 text-[10px] text-red-200/55">
              <summary className="cursor-pointer font-medium">Technical details</summary>
              <p className="mt-2 break-words font-mono">{code ?? "unknown_failure"}{technical ? ` · ${technical}` : ""}</p>
            </details>
          )}
        </div>
      </div>
    </section>
  );
}

function DetailSkeleton() {
  return <div className="min-h-screen bg-[#09090d] px-5 py-8"><div className="mx-auto max-w-7xl animate-pulse"><div className="h-3 w-32 rounded bg-white/[0.05]" /><div className="mt-10 h-6 w-2/3 rounded bg-white/[0.08]" /><div className="mt-4 h-3 w-48 rounded bg-white/[0.05]" /><div className="mt-10 grid gap-5 xl:grid-cols-[1fr_360px]"><div className="h-96 rounded-2xl bg-white/[0.04]" /><div className="h-80 rounded-2xl bg-white/[0.04]" /></div></div></div>;
}

function DetailState({ title, text, action }: { title: string; text: string; action: React.ReactNode }) {
  return <div className="flex min-h-[70vh] items-center justify-center bg-[#09090d] px-6 text-center text-white"><div><AlertTriangle className="mx-auto h-7 w-7 text-[#8c8ca8]" /><h1 className="mt-5 text-lg font-semibold">{title}</h1><p className="mt-2 max-w-md text-sm leading-6 text-[#8c8ca8]">{text}</p><div className="mt-5">{action}</div></div></div>;
}
