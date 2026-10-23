"use client";

import { Database, FileText, LoaderCircle, Plus, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { useWorkspace } from "@/components/workspace-provider";
import { apiFetch, type DataSource, type Document } from "@/lib/api";

function formatDate(value: string | null) {
  return value ? new Date(value).toLocaleString() : "No imports yet";
}

export default function DataSourcesPage() {
  const { workspace, cacheKey } = useWorkspace();
  const fileInput = useRef<HTMLInputElement>(null);
  const [sources, setSources] = useState<DataSource[]>([]);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [selectedSourceId, setSelectedSourceId] = useState("");
  const [name, setName] = useState("");
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");

  const loadSources = useCallback(async (preferredId?: string) => {
    const available = await apiFetch<DataSource[]>("/api/v1/data-sources");
    setSources(available);
    setSelectedSourceId((current) => {
      const desired = preferredId ?? current;
      return available.some((source) => source.id === desired)
        ? desired
        : (available[0]?.id ?? "");
    });
  }, []);

  useEffect(() => {
    setSources([]);
    setDocuments([]);
    setSelectedSourceId("");
    setError("");
    setLoading(true);
    void loadSources()
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Could not load data sources.");
      })
      .finally(() => setLoading(false));
  }, [cacheKey, loadSources]);

  useEffect(() => {
    if (!selectedSourceId) {
      setDocuments([]);
      return;
    }
    void apiFetch<Document[]>(
      `/api/v1/documents?data_source_id=${encodeURIComponent(selectedSourceId)}`
    )
      .then(setDocuments)
      .catch((caught) => {
        setError(caught instanceof Error ? caught.message : "Could not load source documents.");
      });
  }, [selectedSourceId, cacheKey]);

  async function createSource() {
    if (!name.trim() || creating || workspace?.is_demo) return;
    try {
      setCreating(true);
      setError("");
      const created = await apiFetch<DataSource>("/api/v1/data-sources", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, source_type: "upload" }),
      });
      setName("");
      await loadSources(created.id);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not create data source.");
    } finally {
      setCreating(false);
    }
  }

  async function uploadDocument(file?: File) {
    if (!file || !selectedSourceId || uploading || workspace?.is_demo) return;
    const form = new FormData();
    form.append("file", file);
    form.append("data_source_id", selectedSourceId);
    try {
      setUploading(true);
      setError("");
      await apiFetch<Document>("/api/v1/documents/upload", {
        method: "POST",
        body: form,
      });
      const refreshed = await apiFetch<Document[]>(
        `/api/v1/documents?data_source_id=${encodeURIComponent(selectedSourceId)}`
      );
      setDocuments(refreshed);
      await loadSources(selectedSourceId);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Document import failed.");
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const selectedSource = sources.find((source) => source.id === selectedSourceId) ?? null;

  return (
    <div className="min-h-screen bg-[#09090d] px-5 py-6 text-white sm:px-8 sm:py-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#7c7cf8]">
            Import foundation
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Data Sources</h1>
          <p className="mt-2 text-sm text-[#8c8ca8]">
            Organize imported documents while Ask and Investigate continue across the workspace.
          </p>
        </div>

        {error && (
          <div className="mb-5 flex items-start justify-between rounded-xl border border-red-400/20 bg-red-400/[0.07] px-4 py-3 text-sm text-red-200">
            <span>{error}</span>
            <button type="button" onClick={() => setError("")} aria-label="Dismiss error">
              <X className="h-4 w-4" />
            </button>
          </div>
        )}

        {!workspace?.is_demo && (
          <section className="mb-7 rounded-2xl border border-white/[0.07] bg-[#0f0f14] p-5">
            <h2 className="text-sm font-semibold">Create an upload source</h2>
            <div className="mt-4 flex flex-col gap-3 sm:flex-row">
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") void createSource();
                }}
                maxLength={120}
                placeholder="Source name, e.g. Customer contracts"
                className="min-w-0 flex-1 rounded-xl border border-white/[0.09] bg-[#09090d] px-4 py-2.5 text-sm outline-none focus:border-[#7c7cf8]/50"
              />
              <button
                type="button"
                onClick={() => void createSource()}
                disabled={!name.trim() || creating}
                className="flex items-center justify-center gap-2 rounded-xl bg-[#7c7cf8] px-4 py-2.5 text-sm font-semibold disabled:opacity-40"
              >
                {creating ? (
                  <LoaderCircle className="h-4 w-4 animate-spin" />
                ) : (
                  <Plus className="h-4 w-4" />
                )}
                Create source
              </button>
            </div>
          </section>
        )}

        <div className="grid gap-6 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <section>
            <h2 className="mb-3 text-xs font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/70">
              Workspace sources
            </h2>
            <div className="space-y-3">
              {loading ? (
                <div className="flex justify-center rounded-2xl border border-white/[0.07] bg-[#0f0f14] py-12">
                  <LoaderCircle className="h-5 w-5 animate-spin text-[#8c8ca8]" />
                </div>
              ) : sources.length === 0 ? (
                <div className="rounded-2xl border border-white/[0.07] bg-[#0f0f14] px-5 py-10 text-center text-sm text-[#8c8ca8]">
                  No data sources yet. Create one to organize future uploads.
                </div>
              ) : (
                sources.map((source) => (
                  <button
                    type="button"
                    key={source.id}
                    onClick={() => setSelectedSourceId(source.id)}
                    className={`w-full rounded-2xl border p-4 text-left transition ${
                      selectedSourceId === source.id
                        ? "border-[#7c7cf8]/45 bg-[#7c7cf8]/[0.08]"
                        : "border-white/[0.07] bg-[#0f0f14] hover:border-white/[0.13]"
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      <div className="flex h-9 w-9 items-center justify-center rounded-[10px] bg-white/[0.045]">
                        <Database className="h-4 w-4 text-[#a5a5b7]" />
                      </div>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium">{source.name}</p>
                        <p className="mt-1 text-xs capitalize text-[#8c8ca8]">
                          {source.source_type.replace("_", " ")} · {source.status}
                        </p>
                        <p className="mt-2 text-[11px] text-[#8c8ca8]/60">
                          Last import: {formatDate(source.last_synced_at)}
                        </p>
                        {source.error && (
                          <p className="mt-2 text-xs text-red-300">{source.error}</p>
                        )}
                      </div>
                    </div>
                  </button>
                ))
              )}
            </div>
          </section>

          <section>
            <div className="mb-3 flex items-center justify-between">
              <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/70">
                Source documents
              </h2>
              <span className="text-xs text-[#8c8ca8]/50">{documents.length}</span>
            </div>
            <div className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f0f14]">
              {selectedSource?.source_type === "upload" && !workspace?.is_demo && (
                <div className="border-b border-white/[0.055] p-4">
                  <button
                    type="button"
                    onClick={() => fileInput.current?.click()}
                    disabled={uploading}
                    className="flex w-full items-center justify-center gap-2 rounded-xl border border-dashed border-[#7c7cf8]/30 bg-[#7c7cf8]/[0.05] px-4 py-3 text-sm font-medium text-[#aaaaff] disabled:opacity-50"
                  >
                    {uploading ? (
                      <LoaderCircle className="h-4 w-4 animate-spin" />
                    ) : (
                      <Upload className="h-4 w-4" />
                    )}
                    {uploading ? "Processing document…" : `Import into ${selectedSource.name}`}
                  </button>
                  <input
                    ref={fileInput}
                    type="file"
                    accept=".pdf,.docx,.txt,.md,.csv"
                    className="hidden"
                    onChange={(event) => void uploadDocument(event.target.files?.[0])}
                  />
                </div>
              )}
              {selectedSource && workspace?.is_demo && (
                <div className="border-b border-white/[0.055] px-4 py-3 text-xs text-[#8c8ca8]">
                  The demo source and its documents are read-only.
                </div>
              )}
              {selectedSource?.source_type === "local_fixture" && !workspace?.is_demo && (
                <div className="border-b border-white/[0.055] px-4 py-3 text-xs text-[#8c8ca8]">
                  This local acceptance source is managed by the operator importer.
                </div>
              )}
              {!selectedSource ? (
                <div className="px-6 py-12 text-center text-sm text-[#8c8ca8]">
                  Select or create a source to view its documents.
                </div>
              ) : documents.length === 0 ? (
                <div className="px-6 py-12 text-center text-sm text-[#8c8ca8]">
                  No documents imported through this source yet.
                </div>
              ) : (
                documents.map((document, index) => (
                  <div
                    key={document.id}
                    className={`flex items-center gap-3 px-4 py-4 ${index ? "border-t border-white/[0.055]" : ""}`}
                  >
                    <FileText className="h-4 w-4 flex-shrink-0 text-[#a5a5b7]" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-sm font-medium">{document.filename}</p>
                      <p className="mt-1 text-xs capitalize text-[#8c8ca8]/65">
                        {document.status}
                      </p>
                      {document.source_synced_at && (
                        <p className="mt-1 text-[11px] text-[#8c8ca8]/50">
                          Synced {formatDate(document.source_synced_at)}
                        </p>
                      )}
                    </div>
                  </div>
                ))
              )}
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
