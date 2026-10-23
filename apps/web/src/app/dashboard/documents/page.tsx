"use client";

import { FileText, LoaderCircle, Upload, X } from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";

import { apiFetch } from "@/lib/api";
import { useWorkspace } from "@/components/workspace-provider";

type Document = {
  id: string;
  filename: string;
  content_type: string;
  size_bytes: number;
  status: string;
  created_at: string;
};

function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}

export default function DocumentsPage() {
  const { workspace, cacheKey } = useWorkspace();
  const inputRef = useRef<HTMLInputElement>(null);
  const [documents, setDocuments] = useState<Document[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState("");

  const loadDocuments = useCallback(async () => {
    try {
      setError("");
      setDocuments(await apiFetch<Document[]>("/api/v1/documents"));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load documents.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setDocuments([]);
    setLoading(true);
    void loadDocuments();
  }, [cacheKey, loadDocuments]);

  async function uploadDocument(file?: File) {
    if (!file || uploading) return;

    const formData = new FormData();
    formData.append("file", file);

    try {
      setUploading(true);
      setError("");
      await apiFetch<Document>("/api/v1/documents/upload", {
        method: "POST",
        body: formData,
      });
      await loadDocuments();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed.");
    } finally {
      setUploading(false);
      if (inputRef.current) inputRef.current.value = "";
    }
  }

  return (
    <div className="min-h-screen bg-[#09090d] px-5 py-6 text-white sm:px-8 sm:py-8">
      <div className="mx-auto max-w-5xl">
        <div className="mb-8">
          <p className="mb-2 text-[11px] font-medium uppercase tracking-[0.14em] text-[#7c7cf8]">
            Knowledge base
          </p>
          <h1 className="text-2xl font-semibold tracking-tight">Documents</h1>
          <p className="mt-2 text-sm text-[#8c8ca8]">
            Add source material for grounded answers and citations.
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

        <button
          type="button"
          onClick={() => inputRef.current?.click()}
          onDragEnter={() => setDragging(true)}
          onDragLeave={() => setDragging(false)}
          onDragOver={(event) => event.preventDefault()}
          onDrop={(event) => {
            event.preventDefault();
            setDragging(false);
            void uploadDocument(event.dataTransfer.files[0]);
          }}
          disabled={uploading || workspace?.is_demo}
          className={`group flex w-full flex-col items-center justify-center rounded-2xl border border-dashed px-6 py-12 transition sm:py-14 ${
            dragging
              ? "border-[#7c7cf8]/70 bg-[#7c7cf8]/10"
              : "border-white/[0.1] bg-white/[0.018] hover:border-[#7c7cf8]/40 hover:bg-white/[0.028]"
          }`}
        >
          <div className="mb-4 flex h-11 w-11 items-center justify-center rounded-xl border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
            {uploading ? (
              <LoaderCircle className="h-5 w-5 animate-spin text-[#7c7cf8]" />
            ) : (
              <Upload className="h-5 w-5 text-[#7c7cf8]" />
            )}
          </div>
          <p className="text-sm font-medium">
            {workspace?.is_demo
              ? "Demo documents are read-only"
              : uploading
                ? "Processing and indexing document…"
                : "Drop a file here or choose a file"}
          </p>
          <p className="mt-2 text-xs text-[#8c8ca8]">
            PDF, DOCX, TXT, Markdown, or CSV · up to 20 MB
          </p>
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.docx,.txt,.md,.csv"
          className="hidden"
          onChange={(event) => void uploadDocument(event.target.files?.[0])}
        />

        <section className="mt-9">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-xs font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/70">
              Indexed documents
            </h2>
            {!loading && <span className="text-xs text-[#8c8ca8]/50">{documents.length}</span>}
          </div>

          <div className="overflow-hidden rounded-2xl border border-white/[0.07] bg-[#0f0f14]">
            {loading ? (
              <div className="flex items-center justify-center py-12 text-[#8c8ca8]">
                <LoaderCircle className="h-5 w-5 animate-spin" />
              </div>
            ) : documents.length === 0 ? (
              <div className="px-6 py-12 text-center text-sm text-[#8c8ca8]">
                No documents indexed yet.
              </div>
            ) : (
              documents.map((document, index) => (
                <div
                  key={document.id}
                  className={`flex items-center gap-4 px-4 py-4 sm:px-5 ${index ? "border-t border-white/[0.055]" : ""}`}
                >
                  <div className="flex h-9 w-9 flex-shrink-0 items-center justify-center rounded-[10px] bg-white/[0.045]">
                    <FileText className="h-4 w-4 text-[#a5a5b7]" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <p className="truncate text-sm font-medium text-[#eeeeF2]">{document.filename}</p>
                    <p className="mt-1 text-xs text-[#8c8ca8]/65">
                      {formatBytes(document.size_bytes)} · {new Date(document.created_at).toLocaleDateString()}
                    </p>
                  </div>
                  <span className="rounded-full border border-emerald-400/15 bg-emerald-400/[0.07] px-2.5 py-1 text-[10px] font-medium capitalize text-emerald-300">
                    {document.status}
                  </span>
                </div>
              ))
            )}
          </div>
        </section>
      </div>
    </div>
  );
}
