import { apiFetch } from "@/lib/api";

export type InvestigationStatus = "queued" | "running" | "completed" | "failed";
export type StepStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type ClaimClassification = "fact" | "derived" | "hypothesis";
export type ValidationStatus = "validated" | "rejected" | "insufficient_evidence";
export type ConfidenceLevel = "low" | "medium" | "high";

export type InvestigationCreated = {
  id: string;
  question: string;
  status: InvestigationStatus;
  created_at: string;
};

export type InvestigationHistoryItem = InvestigationCreated & {
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  intent_summary: string | null;
  brief_preview: string | null;
  confidence_score: number | null;
  confidence_level: ConfidenceLevel | null;
};

export type InvestigationHistoryResponse = {
  items: InvestigationHistoryItem[];
  next_cursor: string | null;
};

export type InvestigationStep = {
  sequence: number;
  tool: string;
  description: string;
  required: boolean;
  depends_on: number[];
  status: StepStatus;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  error: string | null;
  started_at: string | null;
  completed_at: string | null;
};

export type EvidenceItem = {
  id: string;
  step_id: string | null;
  evidence_kind: string;
  source_kind: string;
  source_id: string | null;
  provenance_group: string;
  source_locator: Record<string, unknown>;
  related_entity_ids: string[];
  content: string | null;
  payload: Record<string, unknown>;
  observed_at: string | null;
};

export type Claim = {
  id: string;
  classification: ClaimClassification;
  statement: string;
  confidence: number | null;
  formula: string | null;
  details: Record<string, unknown>;
  validation_status: ValidationStatus;
  evidence_ids: string[];
};

export type SupportedBriefStatement = {
  text: string;
  claim_ids: string[];
};

export type ExecutiveBrief = {
  what_happened: SupportedBriefStatement;
  primary_driver: SupportedBriefStatement | null;
  likely_explanation: SupportedBriefStatement | null;
  confidence: {
    score: number;
    level: ConfidenceLevel;
    rationale: string;
  };
  key_evidence: Array<{
    evidence_id: string;
    label: string;
    claim_ids: string[];
  }>;
  uncertainties: Array<{ text: string; claim_ids: string[] }>;
  recommended_follow_up_questions: string[];
};

export type InvestigationDetail = InvestigationCreated & {
  updated_at: string;
  started_at: string | null;
  completed_at: string | null;
  failure_code: string | null;
  error: string | null;
  intent: Record<string, unknown> | null;
  assumptions: string[];
  plan: Record<string, unknown> | null;
  execution_usage: Record<string, unknown>;
  steps: InvestigationStep[];
  claims: Claim[];
  evidence: EvidenceItem[];
  executive_brief: ExecutiveBrief | null;
  evidence_graph: { nodes: unknown[]; edges: unknown[] };
};

export async function createInvestigation(question: string) {
  return apiFetch<InvestigationCreated>("/api/v1/investigations", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question }),
  });
}

export async function getInvestigation(id: string) {
  return apiFetch<InvestigationDetail>(`/api/v1/investigations/${id}`);
}

export async function listInvestigations(cursor?: string) {
  const search = new URLSearchParams({ limit: "20" });
  if (cursor) search.set("cursor", cursor);
  return apiFetch<InvestigationHistoryResponse>(`/api/v1/investigations?${search}`);
}

export const toolLabels: Record<string, string> = {
  query_metric_series: "Query revenue series",
  calculate_metric_change: "Calculate metric change",
  rank_entity_contributions: "Rank entity contributions",
  query_related_records: "Review related records",
  semantic_document_search: "Search supporting documents",
  traverse_relationships: "Trace company relationships",
};

export function humanize(value: string) {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export function formatDateTime(value: string | null) {
  if (!value) return "Not available";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(new Date(value));
}

export function formatDuration(start: string | null, end: string | null) {
  if (!start || !end) return null;
  const seconds = Math.max(0, (new Date(end).getTime() - new Date(start).getTime()) / 1000);
  return seconds < 60 ? `${seconds.toFixed(1)}s` : `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

export function failureMessage(code: string | null, fallback: string | null) {
  const messages: Record<string, string> = {
    enqueue_failed: "ORION could not queue this investigation. Check the worker and Redis connection.",
    invalid_plan: "ORION could not create a supported investigation plan for this question.",
    unsupported_metric: "Phase 3 currently supports recognized-revenue investigations only.",
    missing_required_data: "The available company data was not sufficient to complete this investigation.",
    execution_limit_exceeded: "The investigation reached its bounded execution limit.",
    soft_timeout: "The investigation exceeded its execution time limit.",
  };
  return (code && messages[code]) || fallback || "The investigation could not be completed.";
}
