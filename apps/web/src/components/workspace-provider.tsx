"use client";

import { useAuth } from "@clerk/nextjs";
import { usePathname, useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";

import { apiFetch, setApiTokenProvider, workspaceStorageKey } from "@/lib/api";
import { isClerkConfigured } from "@/lib/auth";

export type Workspace = {
  id: string;
  name: string;
  industry: string | null;
  is_demo: boolean;
  created_at: string;
  updated_at: string;
};

type WorkspaceContextValue = {
  workspaces: Workspace[];
  workspace: Workspace | null;
  loading: boolean;
  cacheKey: number;
  selectWorkspace: (workspace: Workspace) => void;
  refreshWorkspaces: () => Promise<Workspace[]>;
};

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function WorkspaceProviderBase({
  children,
  getToken,
}: {
  children: React.ReactNode;
  getToken: () => Promise<string | null>;
}) {
  const pathname = usePathname();
  const router = useRouter();
  const [workspaces, setWorkspaces] = useState<Workspace[]>([]);
  const [workspace, setWorkspace] = useState<Workspace | null>(null);
  const [loading, setLoading] = useState(true);
  const [cacheKey, setCacheKey] = useState(0);

  useEffect(() => {
    setApiTokenProvider(getToken);
    return () => setApiTokenProvider(null);
  }, [getToken]);

  const refreshWorkspaces = useCallback(async () => {
    const available = await apiFetch<Workspace[]>("/api/v1/workspaces");
    setWorkspaces(available);
    const persisted = window.localStorage.getItem(workspaceStorageKey);
    const selected = available.find((item) => item.id === persisted) ?? null;
    if (!selected && persisted) window.localStorage.removeItem(workspaceStorageKey);
    setWorkspace(selected);
    return available;
  }, []);

  useEffect(() => {
    void refreshWorkspaces().finally(() => setLoading(false));
  }, [refreshWorkspaces]);

  useEffect(() => {
    if (!loading && !workspace && pathname !== "/dashboard/onboarding") {
      router.replace("/dashboard/onboarding");
    }
  }, [loading, pathname, router, workspace]);

  const selectWorkspace = useCallback(
    (next: Workspace) => {
      window.localStorage.setItem(workspaceStorageKey, next.id);
      setWorkspace(next);
      setCacheKey((value) => value + 1);
      router.push("/dashboard/chat");
    },
    [router]
  );

  const value = useMemo(
    () => ({ workspaces, workspace, loading, cacheKey, selectWorkspace, refreshWorkspaces }),
    [workspaces, workspace, loading, cacheKey, selectWorkspace, refreshWorkspaces]
  );

  if (loading && pathname !== "/dashboard/onboarding") {
    return <div className="min-h-screen bg-[#09090d]" />;
  }
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

function ClerkWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const { getToken } = useAuth();
  return <WorkspaceProviderBase getToken={getToken}>{children}</WorkspaceProviderBase>;
}

function LocalWorkspaceProvider({ children }: { children: React.ReactNode }) {
  const getToken = useCallback(async () => null, []);
  return <WorkspaceProviderBase getToken={getToken}>{children}</WorkspaceProviderBase>;
}

export function WorkspaceProvider({ children }: { children: React.ReactNode }) {
  return isClerkConfigured ? (
    <ClerkWorkspaceProvider>{children}</ClerkWorkspaceProvider>
  ) : (
    <LocalWorkspaceProvider>{children}</LocalWorkspaceProvider>
  );
}

export function useWorkspace() {
  const value = useContext(WorkspaceContext);
  if (!value) throw new Error("useWorkspace must be used inside WorkspaceProvider");
  return value;
}
