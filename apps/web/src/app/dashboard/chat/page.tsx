"use client";

import {
  ArrowUp,
  BookOpen,
  FileText,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";

import { apiFetch, type AskRequest, type AskResponse, type AskSource } from "@/lib/api";
import { useWorkspace } from "@/components/workspace-provider";

export default function ChatPage() {
  const { cacheKey } = useWorkspace();
  const [input, setInput] = useState("");
  const [question, setQuestion] = useState("");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<AskSource[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    setInput("");
    setQuestion("");
    setAnswer("");
    setSources([]);
    setError("");
  }, [cacheKey]);

  async function handleSubmit() {
    const submittedQuestion = input.trim();

    if (!submittedQuestion || loading) {
      return;
    }

    try {
      setLoading(true);
      setError("");
      setQuestion(submittedQuestion);
      setInput("");
      setAnswer("");
      setSources([]);

      const request: AskRequest = {
        question: submittedQuestion,
        limit: 5,
      };
      const data = await apiFetch<AskResponse>("/api/v1/ask", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify(request),
      });

      setAnswer(data.answer ?? "");
      setSources(data.sources ?? []);
      setInput("");
    } catch (err) {
      setError(
        err instanceof Error
          ? err.message
          : "Something went wrong while asking ORION."
      );
    } finally {
      setLoading(false);
    }
  }

  function handleNewChat() {
    setInput("");
    setQuestion("");
    setAnswer("");
    setSources([]);
    setError("");
  }

  return (
    <div className="flex h-[calc(100dvh-3.5rem)] flex-col overflow-hidden bg-[#09090d] text-white md:h-screen">
      {/* Header */}
      <header className="flex flex-shrink-0 items-center justify-between border-b border-white/[0.055] bg-[#09090d]/90 px-9 py-4 backdrop-blur-sm">
        <div>
          <h1 className="text-[14px] font-semibold tracking-tight">
            Ask ORION
          </h1>

          <div className="mt-[3px] flex items-center gap-1.5">
            <span className="h-[6px] w-[6px] rounded-full bg-emerald-400" />

            <span className="text-[11.5px] text-[#8c8ca8]">
              Company knowledge connected
            </span>
          </div>
        </div>

        <Link
          href="/dashboard/documents"
          className="flex items-center gap-2 rounded-[9px] border border-white/[0.08] bg-white/[0.02] px-3 py-[7px] text-[12.5px] text-[#8c8ca8] transition hover:border-white/[0.14] hover:text-white"
        >
          <BookOpen className="h-[13px] w-[13px]" />
          Documents
        </Link>
      </header>

      {/* Conversation */}
      <div className="flex-1 overflow-y-auto">
        <div className="mx-auto flex min-h-full max-w-[880px] flex-col px-8 py-10">
          {/* Empty state */}
          {!question && !loading && (
            <div className="flex flex-1 flex-col items-center justify-center pb-24 text-center">
              <div className="mb-5 flex h-11 w-11 items-center justify-center rounded-[13px] border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
                <Zap
                  className="h-5 w-5 text-[#7c7cf8]"
                  strokeWidth={2}
                />
              </div>

              <h2 className="text-[25px] font-semibold tracking-[-0.025em] text-white">
                What can I help you find?
              </h2>

              <p className="mt-3 max-w-md text-[14px] leading-6 text-[#8c8ca8]">
                Ask questions about your uploaded documents and get answers
                grounded in your company knowledge.
              </p>
            </div>
          )}

          {/* Question */}
          {question && (
            <div className="mb-10 flex justify-end">
              <div className="max-w-[640px]">
                <div className="rounded-[18px] rounded-tr-[5px] border border-white/[0.072] bg-[#1c1c24] px-5 py-[14px]">
                  <p className="text-[14px] leading-[1.65] text-white">
                    {question}
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Error */}
          {error && (
            <div className="mb-8 rounded-[12px] border border-red-400/20 bg-red-400/[0.07] px-4 py-3 text-[13px] leading-6 text-red-200">
              {error}
            </div>
          )}

          {/* Loading */}
          {loading && (
            <div className="flex gap-[14px]">
              <AdminAvatar />

              <div className="pt-1">
                <p className="text-[12px] font-semibold text-[#8c8ca8]">
                  ORION
                </p>

                <div className="mt-4 flex items-center gap-2">
                  <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-[#7c7cf8]" />
                  <span className="text-[13.5px] text-[#8c8ca8]">
                    Searching your documents...
                  </span>
                </div>
              </div>
            </div>
          )}

          {/* Real answer */}
          {answer && !loading && (
            <div className="flex gap-[14px]">
              <AdminAvatar />

              <div className="min-w-0 flex-1">
                <div className="mb-4">
                  <span className="text-[12px] font-semibold text-[#8c8ca8]">
                    ORION
                  </span>
                </div>

                {/* Markdown answer */}
                <div className="text-[14.5px] leading-[1.75] text-[#eeeeF2]">
                  <ReactMarkdown
                    components={{
                      h1: ({ children }) => (
                        <h1 className="mb-3 mt-6 text-xl font-semibold">
                          {children}
                        </h1>
                      ),

                      h2: ({ children }) => (
                        <h2 className="mb-3 mt-6 text-[16px] font-semibold">
                          {children}
                        </h2>
                      ),

                      h3: ({ children }) => (
                        <h3 className="mb-2 mt-5 text-[14.5px] font-semibold">
                          {children}
                        </h3>
                      ),

                      p: ({ children }) => (
                        <p className="mb-4 leading-[1.75] last:mb-0">
                          {children}
                        </p>
                      ),

                      strong: ({ children }) => (
                        <strong className="font-semibold text-white">
                          {children}
                        </strong>
                      ),

                      ul: ({ children }) => (
                        <ul className="mb-4 ml-5 list-disc space-y-2 text-[#d8d8e0]">
                          {children}
                        </ul>
                      ),

                      ol: ({ children }) => (
                        <ol className="mb-4 ml-5 list-decimal space-y-2 text-[#d8d8e0]">
                          {children}
                        </ol>
                      ),

                      li: ({ children }) => (
                        <li className="pl-1 leading-[1.7]">
                          {children}
                        </li>
                      ),

                      blockquote: ({ children }) => (
                        <blockquote className="my-4 border-l-2 border-[#7c7cf8]/35 pl-4 text-[#a9a9ba]">
                          {children}
                        </blockquote>
                      ),

                      code: ({ children }) => (
                        <code className="rounded bg-white/[0.06] px-1.5 py-0.5 font-mono text-[12.5px] text-[#d4d4dd]">
                          {children}
                        </code>
                      ),
                    }}
                  >
                    {answer}
                  </ReactMarkdown>
                </div>

                {/* Sources */}
                {sources.length > 0 && (
                  <div className="mt-8">
                    <div className="mb-3 flex items-center gap-2">
                      <span className="text-[10.5px] font-semibold uppercase tracking-[0.12em] text-[#8c8ca8]/55">
                        Sources
                      </span>

                      <div className="h-px flex-1 bg-white/[0.05]" />
                    </div>

                    <div className="grid grid-cols-1 gap-[10px] sm:grid-cols-2">
                      {sources.map((source, index) => {
                        const sourceContent =
                          source.snippet ??
                          source.content ??
                          "Relevant passage retrieved from this document.";

                        const sourceTitle =
                          source.title ??
                          source.filename ??
                          source.file ??
                          `Source ${index + 1}`;

                        return (
                          <div
                            key={
                              source.chunk_id ??
                              source.id ??
                              `${source.document_id ?? "source"}-${source.chunk_index ?? index}`
                            }
                            className="group rounded-[12px] border border-white/[0.07] bg-[#0f0f14] p-[14px] transition-all duration-200 hover:border-[#7c7cf8]/30 hover:bg-[#111116]"
                          >
                            <div className="mb-[10px] flex items-center gap-[9px]">
                              <div className="flex h-[24px] w-[24px] flex-shrink-0 items-center justify-center rounded-[7px] border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
                                <span className="text-[10px] font-bold text-[#7c7cf8]">
                                  {index + 1}
                                </span>
                              </div>

                              <div className="min-w-0 flex-1">
                                <p className="truncate text-[12px] font-semibold text-white">
                                  {sourceTitle}
                                </p>

                                <p className="mt-[2px] text-[10.5px] text-[#8c8ca8]/50">
                                  {source.page
                                    ? `Page ${source.page}`
                                    : source.chunk_index !== undefined
                                      ? `Chunk ${source.chunk_index}`
                                      : "Document source"}
                                </p>
                              </div>
                            </div>

                            <p className="line-clamp-4 text-[11.5px] leading-[1.65] text-[#8c8ca8]">
                              {sourceContent}
                            </p>

                            {source.document_id && (
                              <div className="mt-3 flex items-center gap-1.5 border-t border-white/[0.05] pt-2.5">
                                <FileText className="h-3 w-3 text-[#8c8ca8]/35" />

                                <span className="truncate text-[10px] text-[#8c8ca8]/40">
                                  {source.document_id}
                                </span>
                              </div>
                            )}
                          </div>
                        );
                      })}
                    </div>
                  </div>
                )}

                {/* New chat */}
                <button
                  type="button"
                  onClick={handleNewChat}
                  className="mt-7 text-[12px] font-medium text-[#7c7cf8] transition hover:text-[#9999ff]"
                >
                  Start a new conversation
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Composer */}
      <div className="flex-shrink-0 bg-[#09090d] px-9 pb-6 pt-3">
        <div className="mx-auto max-w-[880px]">
          <div className="relative rounded-[16px] border border-white/[0.08] bg-[#111116] transition-all duration-200 focus-within:border-[#7c7cf8]/30 focus-within:shadow-[0_0_0_3px_rgba(124,124,248,0.07)]">
            <textarea
              value={input}
              onChange={(event) => {
                setInput(event.target.value);

                event.target.style.height = "auto";

                event.target.style.height =
                  Math.min(event.target.scrollHeight, 200) + "px";
              }}
              onKeyDown={(event) => {
                if (
                  event.key === "Enter" &&
                  !event.shiftKey
                ) {
                  event.preventDefault();
                  handleSubmit();
                }
              }}
              placeholder="Ask anything about your documents..."
              rows={1}
              className="block min-h-[92px] max-h-[200px] w-full appearance-none resize-none border-0 bg-transparent px-5 pb-[48px] pt-4 text-[14px] leading-[1.6] text-white outline-none placeholder:text-[#8c8ca8]/40 focus:border-0 focus:outline-none focus:ring-0"
              style={{
                width: "100%",
                background: "transparent",
                color: "white",
                boxShadow: "none",
              }}
            />

            {/* Composer toolbar */}
            <div className="absolute bottom-0 left-0 right-0 flex items-center justify-between px-4 pb-3">
              <div className="flex items-center gap-1">
                <Link
                  href="/dashboard/documents"
                  className="flex items-center gap-[7px] rounded-lg px-[9px] py-[5px] text-[#8c8ca8]/60 transition-colors hover:bg-white/[0.05] hover:text-[#8c8ca8]"
                >
                  <FileText
                    className="h-[14px] w-[14px]"
                    strokeWidth={1.75}
                  />

                  <span className="text-[12px] font-medium">
                    Add doc
                  </span>
                </Link>
              </div>

              <button
                type="button"
                onClick={handleSubmit}
                disabled={!input.trim() || loading}
                className={`flex h-8 w-8 items-center justify-center rounded-[10px] transition-all duration-150 ${
                  input.trim() && !loading
                    ? "bg-[#7c7cf8] text-white shadow-[0_0_12px_rgba(124,124,248,0.35)] hover:bg-[#8a8afb] active:scale-95"
                    : "cursor-not-allowed bg-white/[0.05] text-[#8c8ca8]/30"
                }`}
                aria-label="Send message"
              >
                <ArrowUp
                  className="h-[14px] w-[14px]"
                  strokeWidth={2.5}
                />
              </button>
            </div>
          </div>

          <p className="mt-[10px] text-center text-[11px] text-[#8c8ca8]/30">
            ORION may make mistakes. Verify important information
            against the original source documents.
          </p>
        </div>
      </div>
    </div>
  );
}

function AdminAvatar() {
  return (
    <div className="mt-[2px] flex-shrink-0">
      <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
        <Zap
          className="h-[13px] w-[13px] text-[#7c7cf8]"
          strokeWidth={2.5}
        />
      </div>
    </div>
  );
}
