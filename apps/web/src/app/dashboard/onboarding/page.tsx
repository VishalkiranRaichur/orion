"use client";

import { Building2, LoaderCircle, Sparkles } from "lucide-react";
import { useState } from "react";

import { useWorkspace, type Workspace } from "@/components/workspace-provider";
import { apiFetch } from "@/lib/api";

export default function OnboardingPage() {
  const { workspaces, selectWorkspace, refreshWorkspaces } = useWorkspace();
  const [name, setName] = useState("");
  const [industry, setIndustry] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const demo = workspaces.find((item) => item.is_demo);

  async function createWorkspace() {
    if (!name.trim() || submitting) return;
    try {
      setSubmitting(true);
      setError("");
      const created = await apiFetch<Workspace>("/api/v1/workspaces", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, industry: industry || null }),
      });
      await refreshWorkspaces();
      selectWorkspace(created);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create workspace.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-screen items-center justify-center bg-[#09090d] px-5 py-12 text-white">
      <div className="w-full max-w-lg rounded-2xl border border-white/[0.08] bg-[#0f0f15] p-7">
        <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-[#7c7cf8]/10">
          <Building2 className="h-5 w-5 text-[#8f8fff]" />
        </div>
        <h1 className="mt-5 text-2xl font-semibold">Set up your company workspace</h1>
        <p className="mt-2 text-sm leading-6 text-[#8c8ca8]">
          Your documents, answers, and investigations stay isolated in this workspace.
        </p>
        <div className="mt-7 space-y-4">
          <input value={name} onChange={(event) => setName(event.target.value)} maxLength={120} placeholder="Company name" className="w-full rounded-xl border border-white/[0.09] bg-[#09090d] px-4 py-3 text-sm outline-none focus:border-[#7c7cf8]/50" />
          <input value={industry} onChange={(event) => setIndustry(event.target.value)} maxLength={120} placeholder="Industry (optional)" className="w-full rounded-xl border border-white/[0.09] bg-[#09090d] px-4 py-3 text-sm outline-none focus:border-[#7c7cf8]/50" />
          {error && <p className="text-xs text-red-300">{error}</p>}
          <button type="button" onClick={() => void createWorkspace()} disabled={!name.trim() || submitting} className="flex w-full items-center justify-center gap-2 rounded-xl bg-[#7c7cf8] px-4 py-3 text-sm font-semibold disabled:opacity-40">
            {submitting && <LoaderCircle className="h-4 w-4 animate-spin" />}
            Create workspace
          </button>
        </div>
        {demo && (
          <button type="button" onClick={() => selectWorkspace(demo)} className="mt-4 flex w-full items-center justify-center gap-2 rounded-xl border border-white/[0.09] px-4 py-3 text-sm font-medium text-[#c7c7d1]">
            <Sparkles className="h-4 w-4 text-[#8f8fff]" /> Explore Demo Company
          </button>
        )}
      </div>
    </div>
  );
}
