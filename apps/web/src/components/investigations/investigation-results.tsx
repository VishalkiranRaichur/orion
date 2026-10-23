"use client";

import {
  AlertTriangle,
  BookOpen,
  Calculator,
  CheckCircle2,
  ChevronRight,
  CircleHelp,
  FileSearch,
  FlaskConical,
  Lightbulb,
  Link2,
} from "lucide-react";
import { useMemo, useState } from "react";

import { ConfidenceIndicator } from "@/components/investigations/status";
import {
  formatDateTime,
  formatDuration,
  humanize,
  toolLabels,
  type Claim,
  type ClaimClassification,
  type EvidenceItem,
  type InvestigationDetail,
} from "@/lib/investigations";
import { cn } from "@/lib/utils";

type Tab = "brief" | "claims" | "evidence" | "activity";

const tabs: Array<{ id: Tab; label: string }> = [
  { id: "brief", label: "Executive brief" },
  { id: "claims", label: "Claims" },
  { id: "evidence", label: "Evidence" },
  { id: "activity", label: "Tool activity" },
];

export function InvestigationResults({ investigation }: { investigation: InvestigationDetail }) {
  const [tab, setTab] = useState<Tab>(investigation.status === "failed" ? "activity" : "brief");
  const [selectedEvidenceId, setSelectedEvidenceId] = useState<string | null>(
    investigation.executive_brief?.key_evidence[0]?.evidence_id ?? investigation.evidence[0]?.id ?? null,
  );
  const evidenceById = useMemo(
    () => new Map(investigation.evidence.map((item) => [item.id, item])),
    [investigation.evidence],
  );
  const selectedEvidence = selectedEvidenceId ? evidenceById.get(selectedEvidenceId) ?? null : null;

  function inspectEvidence(id: string) {
    setSelectedEvidenceId(id);
    setTab("evidence");
  }

  return (
    <section className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f0f14]">
      <div className="overflow-x-auto border-b border-white/[0.06] px-3 sm:px-5">
        <div className="flex min-w-max gap-1" role="tablist" aria-label="Investigation result views">
          {tabs.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={tab === item.id}
              onClick={() => setTab(item.id)}
              className={cn(
                "relative px-3 py-4 text-xs font-medium transition",
                tab === item.id ? "text-white" : "text-[#8c8ca8] hover:text-[#ccccd5]",
              )}
            >
              {item.label}
              {tab === item.id && <span className="absolute inset-x-2 bottom-0 h-0.5 rounded-full bg-[#7c7cf8]" />}
            </button>
          ))}
        </div>
      </div>

      <div className="p-4 sm:p-6">
        {tab === "brief" && <ExecutiveBriefView investigation={investigation} onEvidence={inspectEvidence} />}
        {tab === "claims" && <ClaimsView claims={investigation.claims} onEvidence={inspectEvidence} />}
        {tab === "evidence" && (
          <EvidenceView
            evidence={investigation.evidence}
            selected={selectedEvidence}
            selectedId={selectedEvidenceId}
            onSelect={setSelectedEvidenceId}
          />
        )}
        {tab === "activity" && <ActivityView investigation={investigation} />}
      </div>
    </section>
  );
}

function ExecutiveBriefView({
  investigation,
  onEvidence,
}: {
  investigation: InvestigationDetail;
  onEvidence: (id: string) => void;
}) {
  const brief = investigation.executive_brief;
  if (!brief) {
    return <EmptyPanel icon={FileSearch} title="No Executive Brief available" text="This investigation did not produce a validated brief." />;
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 rounded-xl border border-[#7c7cf8]/15 bg-[#7c7cf8]/[0.045] p-5 sm:flex-row sm:items-start sm:justify-between">
        <div className="max-w-2xl">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-[#8f8fff]">Executive assessment</p>
          <h2 className="mt-3 text-lg font-semibold leading-7 text-white">{brief.what_happened.text}</h2>
          <p className="mt-3 text-xs leading-5 text-[#aaaabd]">{brief.confidence.rationale}</p>
        </div>
        <ConfidenceIndicator score={brief.confidence.score} level={brief.confidence.level} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BriefCard icon={Calculator} eyebrow="Primary driver" statement={brief.primary_driver?.text ?? null} empty="No validated primary driver was identified." />
        <BriefCard icon={Lightbulb} eyebrow="Likely explanation" statement={brief.likely_explanation?.text ?? null} empty="Causal evidence was not strong enough for a validated explanation." />
      </div>

      {brief.key_evidence.length > 0 && (
        <div>
          <SectionTitle title="Key evidence" count={brief.key_evidence.length} />
          <div className="grid gap-3 lg:grid-cols-2">
            {brief.key_evidence.map((item, index) => (
              <button
                key={item.evidence_id}
                type="button"
                onClick={() => onEvidence(item.evidence_id)}
                className="group flex items-start gap-3 rounded-xl border border-white/[0.07] bg-[#111116] p-4 text-left transition hover:border-[#7c7cf8]/25"
              >
                <span className="flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-lg bg-[#7c7cf8]/10 text-[10px] font-bold text-[#8f8fff]">{index + 1}</span>
                <span className="min-w-0 flex-1 text-xs leading-5 text-[#c7c7d1]">{item.label}</span>
                <ChevronRight className="mt-1 h-3.5 w-3.5 text-[#8c8ca8]/30 group-hover:text-[#8f8fff]" />
              </button>
            ))}
          </div>
        </div>
      )}

      {(brief.uncertainties.length > 0 || brief.recommended_follow_up_questions.length > 0) && (
        <div className="grid gap-4 lg:grid-cols-2">
          <ListCard icon={AlertTriangle} title="Uncertainties" items={brief.uncertainties.map((item) => item.text)} tone="amber" empty="No material uncertainties recorded." />
          <ListCard icon={CircleHelp} title="Recommended follow-ups" items={brief.recommended_follow_up_questions} tone="violet" empty="No follow-up questions recommended." />
        </div>
      )}
    </div>
  );
}

function ClaimsView({ claims, onEvidence }: { claims: Claim[]; onEvidence: (id: string) => void }) {
  if (claims.length === 0) return <EmptyPanel icon={FlaskConical} title="No claims produced" text="This investigation has no persisted claims to inspect." />;
  const groups: ClaimClassification[] = ["fact", "derived", "hypothesis"];
  return (
    <div className="space-y-8">
      {groups.map((classification) => {
        const items = claims.filter((claim) => claim.classification === classification);
        return (
          <section key={classification}>
            <SectionTitle title={humanize(classification)} count={items.length} />
            {items.length === 0 ? (
              <p className="rounded-xl border border-dashed border-white/[0.07] px-4 py-5 text-xs text-[#8c8ca8]">No {classification} claims were produced.</p>
            ) : (
              <div className="space-y-3">
                {items.map((claim) => <ClaimCard key={claim.id} claim={claim} onEvidence={onEvidence} />)}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}

function ClaimCard({ claim, onEvidence }: { claim: Claim; onEvidence: (id: string) => void }) {
  const accent = claim.classification === "fact" ? "sky" : claim.classification === "derived" ? "violet" : "amber";
  const accentClasses = {
    sky: "border-sky-400/15 bg-sky-400/[0.035] text-sky-300",
    violet: "border-violet-400/15 bg-violet-400/[0.035] text-violet-300",
    amber: "border-amber-400/15 bg-amber-400/[0.035] text-amber-300",
  }[accent];
  return (
    <article className={cn("rounded-xl border p-4", accentClasses)}>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <p className="text-sm leading-6 text-[#eeeeF2]">{claim.statement}</p>
        <span className="flex-shrink-0 rounded-full border border-current/20 px-2 py-1 text-[9px] font-semibold uppercase tracking-[0.1em]">
          {humanize(claim.validation_status)}
        </span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-3 text-[10px] text-[#8c8ca8]">
        {claim.confidence !== null && <span>{Math.round(claim.confidence * 100)}% confidence</span>}
        {claim.formula && <span className="font-mono">{claim.formula}</span>}
      </div>
      {claim.evidence_ids.length > 0 && (
        <div className="mt-4 flex flex-wrap gap-2">
          {claim.evidence_ids.map((id, index) => (
            <button key={id} type="button" onClick={() => onEvidence(id)} className="inline-flex items-center gap-1.5 rounded-lg border border-white/[0.08] bg-black/10 px-2.5 py-1.5 text-[10px] text-[#aaaabd] hover:border-[#7c7cf8]/25 hover:text-white">
              <Link2 className="h-3 w-3" /> Evidence {index + 1}
            </button>
          ))}
        </div>
      )}
    </article>
  );
}

function EvidenceView({ evidence, selected, selectedId, onSelect }: { evidence: EvidenceItem[]; selected: EvidenceItem | null; selectedId: string | null; onSelect: (id: string) => void }) {
  if (evidence.length === 0) return <EmptyPanel icon={BookOpen} title="No evidence persisted" text="This investigation has no source or calculation evidence." />;
  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)]">
      <div className="max-h-[620px] space-y-2 overflow-y-auto pr-1">
        {evidence.map((item) => (
          <button key={item.id} type="button" onClick={() => onSelect(item.id)} className={cn("w-full rounded-xl border p-3.5 text-left transition", selectedId === item.id ? "border-[#7c7cf8]/35 bg-[#7c7cf8]/[0.07]" : "border-white/[0.07] bg-[#111116] hover:border-white/[0.12]")}>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[10px] font-semibold uppercase tracking-[0.1em] text-[#8f8fff]">{humanize(item.evidence_kind)}</span>
              <span className="truncate text-[9px] text-[#8c8ca8]/45">{humanize(item.source_kind)}</span>
            </div>
            <p className="mt-2 line-clamp-2 text-xs leading-5 text-[#c7c7d1]">{evidenceLabel(item)}</p>
          </button>
        ))}
      </div>
      {selected ? <EvidenceDetail evidence={selected} /> : <EmptyPanel icon={FileSearch} title="Select evidence" text="Choose an evidence item to inspect its provenance." />}
    </div>
  );
}

function EvidenceDetail({ evidence }: { evidence: EvidenceItem }) {
  const locatorEntries = Object.entries(evidence.source_locator).filter(([, value]) => value !== null && value !== "");
  return (
    <article className="rounded-xl border border-white/[0.07] bg-[#09090d] p-5">
      <div className="flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-[#7c7cf8]/20 bg-[#7c7cf8]/[0.08] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.1em] text-[#8f8fff]">{humanize(evidence.evidence_kind)}</span>
        <span className="text-[10px] text-[#8c8ca8]">{humanize(evidence.source_kind)}</span>
      </div>
      <h3 className="mt-4 text-sm font-semibold text-white">{evidenceLabel(evidence)}</h3>
      {evidence.content && <p className="mt-4 whitespace-pre-wrap rounded-xl border border-white/[0.06] bg-white/[0.02] p-4 text-xs leading-6 text-[#c7c7d1]">{evidence.content}</p>}
      <dl className="mt-5 grid gap-3 text-xs sm:grid-cols-2">
        {evidence.observed_at && <Metadata label="Observed" value={formatDateTime(evidence.observed_at)} />}
        <Metadata label="Provenance group" value={evidence.provenance_group} />
        {locatorEntries.map(([key, value]) => <Metadata key={key} label={humanize(key)} value={String(value)} />)}
      </dl>
      <JsonDetails label="Evidence payload" value={evidence.payload} />
    </article>
  );
}

function ActivityView({ investigation }: { investigation: InvestigationDetail }) {
  if (investigation.steps.length === 0) return <EmptyPanel icon={FileSearch} title="No tool activity yet" text="Tool activity appears after ORION persists its investigation plan." />;
  return (
    <div className="space-y-3">
      {investigation.steps.map((step) => (
        <article key={step.sequence} className="rounded-xl border border-white/[0.07] bg-[#111116] p-4">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
            <div>
              <p className="text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8f8fff]">Step {step.sequence} · {toolLabels[step.tool] ?? humanize(step.tool)}</p>
              <h3 className="mt-2 text-sm font-medium text-white">{step.description}</h3>
              <p className="mt-1 text-[10px] text-[#8c8ca8]">{step.required ? "Required" : "Optional"}{step.depends_on.length > 0 ? ` · depends on ${step.depends_on.join(", ")}` : ""}</p>
            </div>
            <div className="text-left text-[10px] text-[#8c8ca8] sm:text-right">
              <p>{humanize(step.status)}</p>
              <p className="mt-1">{formatDuration(step.started_at, step.completed_at) ?? "Duration unavailable"}</p>
            </div>
          </div>
          {step.error && <p className="mt-3 rounded-lg border border-red-400/15 bg-red-400/[0.05] px-3 py-2 text-xs text-red-200">{step.error}</p>}
          <div className="mt-3 grid gap-2 sm:grid-cols-2">
            <JsonDetails label="Tool input" value={step.input} />
            {step.output && <JsonDetails label="Tool output" value={step.output} />}
          </div>
        </article>
      ))}
    </div>
  );
}

function BriefCard({ icon: Icon, eyebrow, statement, empty }: { icon: typeof Lightbulb; eyebrow: string; statement: string | null; empty: string }) {
  return (
    <article className="rounded-xl border border-white/[0.07] bg-[#111116] p-5">
      <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/[0.04]"><Icon className="h-4 w-4 text-[#8f8fff]" /></div>
      <p className="mt-4 text-[10px] font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/60">{eyebrow}</p>
      <p className={cn("mt-2 text-sm leading-6", statement ? "text-[#e5e5eb]" : "text-[#8c8ca8]")}>{statement ?? empty}</p>
    </article>
  );
}

function ListCard({ icon: Icon, title, items, tone, empty }: { icon: typeof AlertTriangle; title: string; items: string[]; tone: "amber" | "violet"; empty: string }) {
  return (
    <article className="rounded-xl border border-white/[0.07] bg-[#111116] p-5">
      <div className="flex items-center gap-2"><Icon className={cn("h-4 w-4", tone === "amber" ? "text-amber-300" : "text-[#8f8fff]")} /><h3 className="text-xs font-semibold text-white">{title}</h3></div>
      {items.length ? <ul className="mt-4 space-y-2">{items.map((item) => <li key={item} className="flex gap-2 text-xs leading-5 text-[#aaaabd]"><span className="mt-2 h-1 w-1 flex-shrink-0 rounded-full bg-current" />{item}</li>)}</ul> : <p className="mt-4 text-xs text-[#8c8ca8]">{empty}</p>}
    </article>
  );
}

function EmptyPanel({ icon: Icon, title, text }: { icon: typeof FileSearch; title: string; text: string }) {
  return <div className="flex flex-col items-center rounded-xl border border-dashed border-white/[0.08] px-6 py-14 text-center"><Icon className="h-6 w-6 text-[#8c8ca8]/50" /><p className="mt-4 text-sm font-medium text-white">{title}</p><p className="mt-2 max-w-sm text-xs leading-5 text-[#8c8ca8]">{text}</p></div>;
}

function SectionTitle({ title, count }: { title: string; count: number }) {
  return <div className="mb-3 flex items-center gap-3"><h3 className="text-xs font-semibold uppercase tracking-[0.1em] text-[#8c8ca8]/65">{title}</h3><span className="rounded-full bg-white/[0.05] px-2 py-0.5 text-[9px] text-[#8c8ca8]">{count}</span><div className="h-px flex-1 bg-white/[0.05]" /></div>;
}

function Metadata({ label, value }: { label: string; value: string }) {
  return <div><dt className="text-[9px] font-semibold uppercase tracking-[0.1em] text-[#8c8ca8]/45">{label}</dt><dd className="mt-1 break-words text-[11px] text-[#aaaabd]">{value}</dd></div>;
}

function JsonDetails({ label, value }: { label: string; value: Record<string, unknown> }) {
  return <details className="mt-4 rounded-lg border border-white/[0.06] bg-white/[0.015] text-xs"><summary className="cursor-pointer px-3 py-2.5 font-medium text-[#8c8ca8] hover:text-white">{label}</summary><pre className="max-h-72 overflow-auto border-t border-white/[0.05] p-3 text-[10px] leading-5 text-[#aaaabd]">{JSON.stringify(value, null, 2)}</pre></details>;
}

function evidenceLabel(evidence: EvidenceItem) {
  const title = evidence.payload.title ?? evidence.payload.filename ?? evidence.payload.entity_name;
  if (typeof title === "string" && title) return title;
  if (evidence.content) return evidence.content;
  return `${humanize(evidence.source_kind)} evidence`;
}
