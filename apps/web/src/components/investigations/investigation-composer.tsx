"use client";

import { ArrowRight, Search, Sparkles } from "lucide-react";
import { useState } from "react";

const examples = [
  "Why did revenue decline in July?",
  "Which customers contributed most to the July revenue change?",
];

export function InvestigationComposer({
  onSubmit,
  submitting,
}: {
  onSubmit: (question: string) => Promise<void>;
  submitting: boolean;
}) {
  const [question, setQuestion] = useState("");
  const [validation, setValidation] = useState("");

  async function submit() {
    const value = question.trim();
    if (value.length < 3) {
      setValidation("Enter a question with at least 3 characters.");
      return;
    }
    if (value.length > 2000) {
      setValidation("Questions must be 2,000 characters or fewer.");
      return;
    }
    setValidation("");
    await onSubmit(value);
  }

  return (
    <section className="relative overflow-hidden rounded-2xl border border-white/[0.08] bg-[#0f0f15] p-5 shadow-2xl shadow-black/20 sm:p-7">
      <div className="pointer-events-none absolute -right-24 -top-24 h-64 w-64 rounded-full bg-[#7c7cf8]/10 blur-3xl" />
      <div className="relative">
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-9 w-9 items-center justify-center rounded-xl border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
            <Sparkles className="h-4 w-4 text-[#8f8fff]" />
          </div>
          <div>
            <h2 className="text-sm font-semibold text-white">Start an investigation</h2>
            <p className="mt-0.5 text-xs text-[#8c8ca8]">
              ORION will plan, retrieve evidence, calculate, and validate its conclusions.
            </p>
          </div>
        </div>

        <div className="rounded-xl border border-white/[0.09] bg-[#09090d] transition focus-within:border-[#7c7cf8]/40 focus-within:ring-4 focus-within:ring-[#7c7cf8]/[0.06]">
          <textarea
            value={question}
            onChange={(event) => {
              setQuestion(event.target.value);
              if (validation) setValidation("");
            }}
            onKeyDown={(event) => {
              if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                event.preventDefault();
                void submit();
              }
            }}
            placeholder="Why did revenue decline in July?"
            rows={4}
            maxLength={2000}
            className="w-full resize-none bg-transparent px-4 pt-4 text-sm leading-6 text-white outline-none placeholder:text-[#8c8ca8]/35"
          />
          <div className="flex items-center justify-between px-3 pb-3">
            <span className="text-[10px] text-[#8c8ca8]/45">
              {question.length > 1800 ? `${question.length}/2000` : "⌘ Enter to investigate"}
            </span>
            <button
              type="button"
              disabled={submitting || !question.trim()}
              onClick={() => void submit()}
              className="inline-flex items-center gap-2 rounded-lg bg-[#7c7cf8] px-3.5 py-2 text-xs font-semibold text-white shadow-[0_0_18px_rgba(124,124,248,0.22)] transition hover:bg-[#8b8bff] disabled:cursor-not-allowed disabled:opacity-40"
            >
              {submitting ? "Creating…" : "Investigate"}
              {!submitting && <ArrowRight className="h-3.5 w-3.5" />}
            </button>
          </div>
        </div>

        {validation && <p className="mt-2 text-xs text-red-300">{validation}</p>}

        <div className="mt-4 flex flex-wrap items-center gap-2">
          <span className="mr-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/45">
            Try
          </span>
          {examples.map((example) => (
            <button
              key={example}
              type="button"
              onClick={() => setQuestion(example)}
              className="inline-flex items-center gap-1.5 rounded-full border border-white/[0.07] bg-white/[0.025] px-3 py-1.5 text-[11px] text-[#aaaabd] transition hover:border-[#7c7cf8]/25 hover:text-white"
            >
              <Search className="h-3 w-3 text-[#7c7cf8]" />
              {example}
            </button>
          ))}
        </div>

        <p className="mt-4 text-[11px] leading-5 text-[#8c8ca8]/55">
          Current investigation scope: recognized-revenue analysis using connected company records and documents.
        </p>
      </div>
    </section>
  );
}
