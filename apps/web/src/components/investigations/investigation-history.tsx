"use client";

import { ArrowRight, History, LoaderCircle, RotateCcw } from "lucide-react";
import Link from "next/link";

import { ConfidenceIndicator, StatusBadge } from "@/components/investigations/status";
import { formatDateTime, humanize, type InvestigationHistoryItem } from "@/lib/investigations";

export function InvestigationHistory({
  items,
  loading,
  loadingMore,
  hasMore,
  error,
  onRetry,
  onLoadMore,
}: {
  items: InvestigationHistoryItem[];
  loading: boolean;
  loadingMore: boolean;
  hasMore: boolean;
  error: string;
  onRetry: () => void;
  onLoadMore: () => void;
}) {
  return (
    <section className="mt-10">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h2 className="text-sm font-semibold text-white">Investigation history</h2>
          <p className="mt-1 text-xs text-[#8c8ca8]">Durable analyses and their evidence-backed outcomes.</p>
        </div>
        {!loading && <span className="text-xs text-[#8c8ca8]/50">{items.length} loaded</span>}
      </div>

      <div className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f0f14]">
        {loading ? (
          <div className="space-y-px bg-white/[0.04]">
            {[0, 1, 2].map((item) => (
              <div key={item} className="animate-pulse bg-[#0f0f14] px-5 py-6">
                <div className="h-3 w-28 rounded bg-white/[0.06]" />
                <div className="mt-4 h-4 w-2/3 rounded bg-white/[0.08]" />
                <div className="mt-3 h-3 w-1/3 rounded bg-white/[0.05]" />
              </div>
            ))}
          </div>
        ) : error && items.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <p className="text-sm text-red-200">{error}</p>
            <button
              type="button"
              onClick={onRetry}
              className="mt-4 inline-flex items-center gap-2 text-xs font-semibold text-[#8f8fff]"
            >
              <RotateCcw className="h-3.5 w-3.5" /> Retry
            </button>
          </div>
        ) : items.length === 0 ? (
          <div className="flex flex-col items-center px-6 py-14 text-center">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-xl bg-white/[0.04]">
              <History className="h-4 w-4 text-[#8c8ca8]" />
            </div>
            <p className="text-sm font-medium text-white">No investigations yet</p>
            <p className="mt-2 max-w-sm text-xs leading-5 text-[#8c8ca8]">
              Ask a supported business question above. Your investigation and evidence trail will appear here.
            </p>
          </div>
        ) : (
          <div className="divide-y divide-white/[0.055]">
            {items.map((item) => (
              <Link
                key={item.id}
                href={`/dashboard/investigate/${item.id}`}
                className="group block px-4 py-5 transition hover:bg-white/[0.025] sm:px-5"
              >
                <div className="flex flex-col gap-4 sm:flex-row sm:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <StatusBadge status={item.status} />
                      {item.intent_summary && (
                        <span className="text-[10px] font-medium uppercase tracking-[0.1em] text-[#8c8ca8]/50">
                          {humanize(item.intent_summary)}
                        </span>
                      )}
                    </div>
                    <h3 className="mt-3 truncate text-sm font-medium text-[#eeeeF2] group-hover:text-white">
                      {item.question}
                    </h3>
                    <p className="mt-1.5 line-clamp-2 text-xs leading-5 text-[#8c8ca8]">
                      {item.brief_preview ??
                        (item.status === "failed"
                          ? "This investigation did not complete. Open it to review the failure."
                          : "ORION is preparing the evidence-backed result.")}
                    </p>
                  </div>
                  <div className="flex flex-shrink-0 items-center justify-between gap-4 sm:justify-end">
                    <div className="text-left sm:text-right">
                      {item.confidence_score !== null && item.confidence_level ? (
                        <ConfidenceIndicator
                          score={item.confidence_score}
                          level={item.confidence_level}
                          compact
                        />
                      ) : (
                        <span className="text-[10px] uppercase tracking-[0.08em] text-[#8c8ca8]/40">
                          Confidence pending
                        </span>
                      )}
                      <p className="mt-2 text-[10px] text-[#8c8ca8]/45">
                        {formatDateTime(item.created_at)}
                      </p>
                    </div>
                    <ArrowRight className="h-4 w-4 text-[#8c8ca8]/30 transition group-hover:translate-x-0.5 group-hover:text-[#7c7cf8]" />
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>

      {error && items.length > 0 && (
        <div className="mt-3 flex items-center justify-between rounded-xl border border-red-400/15 bg-red-400/[0.05] px-4 py-3 text-xs text-red-200">
          <span>{error}</span>
          <button type="button" onClick={onRetry} className="font-semibold text-red-100">
            Retry
          </button>
        </div>
      )}

      {hasMore && (
        <button
          type="button"
          onClick={onLoadMore}
          disabled={loadingMore}
          className="mx-auto mt-5 flex items-center gap-2 rounded-lg border border-white/[0.08] px-4 py-2 text-xs font-medium text-[#aaaabd] transition hover:border-white/[0.14] hover:text-white disabled:opacity-50"
        >
          {loadingMore && <LoaderCircle className="h-3.5 w-3.5 animate-spin" />}
          {loadingMore ? "Loading…" : "Load more"}
        </button>
      )}
    </section>
  );
}
