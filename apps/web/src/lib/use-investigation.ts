"use client";

import { useCallback, useEffect, useState } from "react";

import { getInvestigation, type InvestigationDetail } from "@/lib/investigations";
import { useWorkspace } from "@/components/workspace-provider";

export function useInvestigation(id: string) {
  const { cacheKey } = useWorkspace();
  const [investigation, setInvestigation] = useState<InvestigationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const retryNow = useCallback(() => setRefreshKey((value) => value + 1), []);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let failures = 0;
    let requestActive = false;

    const schedule = (delay: number) => {
      if (!cancelled) timer = setTimeout(() => void poll(), delay);
    };

    const poll = async () => {
      if (cancelled || requestActive || document.hidden) return;
      requestActive = true;
      try {
        const detail = await getInvestigation(id);
        if (cancelled) return;
        setInvestigation(detail);
        setError(null);
        setLoading(false);
        failures = 0;
        if (detail.status === "queued" || detail.status === "running") schedule(2000);
      } catch (caught) {
        if (cancelled) return;
        const nextError = caught instanceof Error ? caught : new Error("Could not load investigation.");
        setError(nextError);
        setLoading(false);
        failures += 1;
        schedule(Math.min(8000, 2000 * 2 ** Math.min(failures - 1, 2)));
      } finally {
        requestActive = false;
      }
    };

    const handleVisibility = () => {
      if (!document.hidden) {
        if (timer) clearTimeout(timer);
        void poll();
      }
    };

    void poll();
    document.addEventListener("visibilitychange", handleVisibility);
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [id, refreshKey, cacheKey]);

  return { investigation, loading, error, retryNow };
}
