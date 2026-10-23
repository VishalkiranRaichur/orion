const configuredApiUrl = process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "");
export const workspaceStorageKey = "orion.activeWorkspaceId";

let tokenProvider: (() => Promise<string | null>) | null = null;

export function setApiTokenProvider(provider: (() => Promise<string | null>) | null) {
  tokenProvider = provider;
}

export const apiUrl = (path: string) => `${configuredApiUrl ?? ""}${path}`;

export type AskSource = {
  id?: string;
  chunk_id?: string;
  document_id?: string;
  chunk_index?: number;
  content?: string;
  snippet?: string;
  file?: string;
  filename?: string;
  title?: string;
  page?: string | number;
};

export type AskRequest = {
  question: string;
  limit: number;
};

export type AskResponse = {
  answer: string;
  sources: AskSource[];
};

export type DataSource = {
  id: string;
  workspace_id: string;
  name: string;
  source_type: "upload" | "demo" | "local_fixture";
  status: "ready" | "error";
  external_key: string | null;
  last_synced_at: string | null;
  error: string | null;
  created_at: string;
  updated_at: string;
};

export type Document = {
  id: string;
  data_source_id: string | null;
  source_item_id: string | null;
  source_modified_at: string | null;
  source_synced_at: string | null;
  filename: string;
  content_type: string;
  size_bytes: number;
  storage_key: string;
  status: string;
  created_at: string;
};

export type ApiErrorDetail =
  | string
  | {
      message?: string;
      investigation_id?: string;
      [key: string]: unknown;
    };

export class ApiError extends Error {
  status: number;
  detail?: ApiErrorDetail;

  constructor(message: string, status: number, detail?: ApiErrorDetail) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    const headers = new Headers(init?.headers);
    if (typeof window !== "undefined") {
      const workspaceId = window.localStorage.getItem(workspaceStorageKey);
      if (workspaceId && !headers.has("X-Workspace-ID")) {
        headers.set("X-Workspace-ID", workspaceId);
      }
    }
    const token = tokenProvider ? await tokenProvider() : null;
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    response = await fetch(apiUrl(path), { ...init, headers });
  } catch {
    throw new Error(
      "Cannot reach the ORION API. Make sure the backend and local services are running."
    );
  }

  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    let detail: ApiErrorDetail | undefined;

    try {
      const body = (await response.json()) as { detail?: ApiErrorDetail };
      detail = body.detail;
      if (typeof detail === "string") {
        message = detail;
      } else if (detail && typeof detail.message === "string") {
        message = detail.message;
      }
    } catch {
      // Keep the status-based fallback for non-JSON responses.
    }

    throw new ApiError(message, response.status, detail);
  }

  return (await response.json()) as T;
}
