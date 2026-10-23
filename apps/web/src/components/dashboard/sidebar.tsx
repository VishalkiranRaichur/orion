"use client";

import {
  Database,
  FileText,
  SearchCheck,
  MessageSquare,
  Plus,
  Settings,
  Upload,
  Zap,
} from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";

import { SidebarUser } from "@/components/dashboard/sidebar-user";
import { WorkspaceSwitcher } from "@/components/dashboard/workspace-switcher";

const navItems = [
  {
    href: "/dashboard/chat",
    label: "Ask AI",
    icon: MessageSquare,
  },
  {
    href: "/dashboard/documents",
    label: "Documents",
    icon: FileText,
  },
  {
    href: "/dashboard/data-sources",
    label: "Data Sources",
    icon: Database,
  },
  {
    href: "/dashboard/investigate",
    label: "Investigate",
    icon: SearchCheck,
  },
  {
    href: "/dashboard/settings",
    label: "Settings",
    icon: Settings,
  },
];

export function Sidebar() {
  const pathname = usePathname();
  const investigating = pathname.startsWith("/dashboard/investigate");

  return (
    <>
      <header className="flex h-14 flex-shrink-0 items-center justify-between border-b border-white/[0.055] bg-sidebar px-4 text-sidebar-foreground md:hidden">
        <Link href="/dashboard/chat" className="flex items-center gap-2">
          <div className="flex h-7 w-7 items-center justify-center rounded-lg border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
            <Zap className="h-3.5 w-3.5 text-[#7c7cf8]" strokeWidth={2.5} />
          </div>
          <span className="text-sm font-semibold">ORION</span>
        </Link>
        <div className="flex items-center gap-2">
          <WorkspaceSwitcher />
        <nav className="flex items-center gap-1" aria-label="Mobile dashboard navigation">
          {navItems.slice(0, 4).map(({ href, label, icon: Icon }) => {
            const active = pathname === href || pathname.startsWith(`${href}/`);
            return (
              <Link
                key={href}
                href={href}
                aria-label={label}
                className={`flex h-9 w-9 items-center justify-center rounded-lg transition ${active ? "bg-white/[0.07] text-[#8f8fff]" : "text-sidebar-foreground/55 hover:text-white"}`}
              >
                <Icon className="h-4 w-4" />
              </Link>
            );
          })}
        </nav>
        </div>
      </header>

      <aside className="hidden h-screen w-[230px] flex-shrink-0 flex-col overflow-hidden border-r border-white/[0.055] bg-sidebar text-sidebar-foreground md:flex">

      {/* Logo */}
      <div className="flex-shrink-0 px-5 pb-1 pt-7">
        <Link
          href="/dashboard/chat"
          className="flex items-center gap-2.5"
        >
          <div className="flex h-7 w-7 flex-shrink-0 items-center justify-center rounded-lg border border-[#7c7cf8]/20 bg-[#7c7cf8]/10">
            <Zap
              className="h-[13px] w-[13px] text-[#7c7cf8]"
              strokeWidth={2.5}
            />
          </div>

          <span className="text-[13.5px] font-semibold tracking-tight">
            ORION
          </span>
        </Link>
      </div>

      <div className="flex-shrink-0 px-3 pt-4">
        <WorkspaceSwitcher />
      </div>

      {/* New Chat */}
      <div className="flex-shrink-0 px-3 pb-1 pt-6">
        <Link
          href={investigating ? "/dashboard/investigate" : "/dashboard/chat"}
          className="flex w-full items-center gap-[9px] rounded-[10px] border border-[#7c7cf8]/20 bg-[#7c7cf8]/10 px-3 py-[7px] text-[13px] font-medium text-[#7c7cf8] transition-all duration-150 hover:bg-[#7c7cf8]/15 active:scale-[0.98]"
        >
          <Plus
            className="h-[14px] w-[14px]"
            strokeWidth={2.5}
          />
          {investigating ? "New investigation" : "New conversation"}
        </Link>
      </div>

      {/* Navigation */}
      <nav className="flex-shrink-0 space-y-[2px] px-3 pt-[18px]">
        {navItems.map(({ href, label, icon: Icon }) => {
          const isActive =
            pathname === href ||
            pathname.startsWith(`${href}/`);

          return (
            <Link
              key={href}
              href={href}
              className={`flex w-full items-center gap-[9px] rounded-[9px] px-3 py-[7px] text-[13px] transition-colors duration-150 ${
                isActive
                  ? "bg-white/[0.06] font-medium text-white"
                  : "text-sidebar-foreground/60 hover:bg-white/[0.04] hover:text-white"
              }`}
            >
              <Icon
                className={`h-[14px] w-[14px] flex-shrink-0 ${
                  isActive ? "text-[#7c7cf8]" : ""
                }`}
                strokeWidth={isActive ? 2.5 : 2}
              />

              {label}
            </Link>
          );
        })}
      </nav>

      <div className="flex-1" />

      {/* Upload Document */}
      <div className="flex-shrink-0 px-3 pb-3 pt-[18px]">
        <Link
          href="/dashboard/documents"
          className="flex w-full items-center gap-[9px] rounded-[9px] border border-dashed border-white/[0.08] px-3 py-[7px] text-[12.5px] text-sidebar-foreground/55 transition-colors hover:bg-white/[0.04] hover:text-white"
        >
          <Upload
            className="h-[13px] w-[13px] flex-shrink-0"
            strokeWidth={1.75}
          />
          Upload document
        </Link>
      </div>

      {/* Existing real user component */}
      <div className="flex-shrink-0 border-t border-white/[0.055] px-3 py-[14px]">
        <SidebarUser />
      </div>
      </aside>
    </>
  );
}
