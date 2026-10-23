"use client";

import { Building2 } from "lucide-react";

import { useWorkspace } from "@/components/workspace-provider";

export function WorkspaceSwitcher() {
  const { workspace, workspaces, selectWorkspace } = useWorkspace();
  if (!workspace) return null;

  return (
    <label className="flex min-w-0 items-center gap-2 rounded-lg border border-white/[0.07] bg-white/[0.025] px-2 py-1.5 text-xs text-[#aaaabd]">
      <Building2 className="h-3.5 w-3.5 flex-shrink-0 text-[#8f8fff]" />
      <select
        aria-label="Active workspace"
        value={workspace.id}
        onChange={(event) => {
          const next = workspaces.find((item) => item.id === event.target.value);
          if (next) selectWorkspace(next);
        }}
        className="min-w-0 max-w-[150px] bg-transparent text-xs outline-none"
      >
        {workspaces.map((item) => (
          <option key={item.id} value={item.id} className="bg-[#15151d]">
            {item.is_demo ? "Explore Demo Company" : item.name}
          </option>
        ))}
      </select>
    </label>
  );
}
