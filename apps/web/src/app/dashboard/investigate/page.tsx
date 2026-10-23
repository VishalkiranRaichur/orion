"use client";

import { Activity, AlertCircle } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { InvestigationComposer } from "@/components/investigations/investigation-composer";
import { InvestigationHistory } from "@/components/investigations/investigation-history";
import { ApiError } from "@/lib/api";
import { useWorkspace } from "@/components/workspace-provider";
import {
  createInvestigation,
  listInvestigations,
  type InvestigationHistoryItem,
} from "@/lib/investigations";

export default function InvestigatePage() {
  const { cacheKey } = useWorkspace();
  const router = useRouter();
  const [items, setItems] = useState<InvestigationHistoryItem[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [historyError, setHistoryError] = useState("");
  const [createError, setCreateError] = useState("");
  const [failedInvestigationId, setFailedInvestigationId] = useState<string | null>(null);

  const loadHistory = useCallback(async (nextCursor?: string) => {
    try {
      if (nextCursor) setLoadingMore(true);
      else setLoading(true);
      setHistoryError("");
      const response = await listInvestigations(nextCursor);
      setItems((current) => (nextCursor ? [...current, ...response.items] : response.items));
      setCursor(response.next_cursor);
    } catch (error) {
      setHistoryError(error instanceof Error ? error.message : "Could not load investigation history.");
    } finally {
      setLoading(false);
      setLoadingMore(false);
    }
  }, []);

  useEffect(() => {
    setItems([]);
    setCursor(null);
    void loadHistory();
  }, [cacheKey, loadHistory]);

  async function handleCreate(question: string) {
    try {
      setSubmitting(true);
      setCreateError("");
      setFailedInvestigationId(null);
      const created = await createInvestigation(question);
      router.push(`/dashboard/investigate/${created.id}`);
    } catch (error) {
      setCreateError(error instanceof Error ? error.message : "Could not create the investigation.");
      if (error instanceof ApiError && typeof error.detail === "object" && error.detail) {
        setFailedInvestigationId(
          typeof error.detail.investigation_id === "string" ? error.detail.investigation_id : null,
        );
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="min-h-screen bg-[#09090d] px-4 py-6 text-white sm:px-7 sm:py-8 lg:px-10">
      <div className="mx-auto max-w-6xl">
        <header className="mb-7 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-[0.15em] text-[#8f8fff]">
              <Activity className="h-3.5 w-3.5" /> Executive intelligence
            </div>
            <h1 className="text-2xl font-semibold tracking-[-0.025em] sm:text-3xl">Investigate</h1>
            <p className="mt-2 max-w-2xl text-sm leading-6 text-[#8c8ca8]">
              Turn a business question into a bounded, evidence-backed investigation and Executive Brief.
            </p>
          </div>
          <Link href="/dashboard/chat" className="text-xs font-medium text-[#8c8ca8] transition hover:text-white">
            Need a document answer? Open Ask →
          </Link>
        </header>

        {createError && (
          <div className="mb-5 flex flex-col gap-3 rounded-xl border border-red-400/20 bg-red-400/[0.06] px-4 py-3 text-xs text-red-200 sm:flex-row sm:items-center sm:justify-between">
            <div className="flex items-start gap-2">
              <AlertCircle className="mt-0.5 h-3.5 w-3.5 flex-shrink-0" />
              <span>{createError}</span>
            </div>
            {failedInvestigationId && (
              <Link href={`/dashboard/investigate/${failedInvestigationId}`} className="flex-shrink-0 font-semibold text-red-100 underline decoration-red-300/30 underline-offset-4">
                View failed record
              </Link>
            )}
          </div>
        )}

        <InvestigationComposer onSubmit={handleCreate} submitting={submitting} />
        <InvestigationHistory
          items={items}
          loading={loading}
          loadingMore={loadingMore}
          hasMore={Boolean(cursor)}
          error={historyError}
          onRetry={() => void loadHistory()}
          onLoadMore={() => cursor && void loadHistory(cursor)}
        />
      </div>
    </div>
  );
}
