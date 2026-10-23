import { Sidebar } from "@/components/dashboard/sidebar";
import { WorkspaceProvider } from "@/components/workspace-provider";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <WorkspaceProvider>
      <div className="flex min-h-screen flex-col bg-[#09090d] text-white md:flex-row">
        <Sidebar />

        <main className="min-h-0 min-w-0 flex-1 overflow-hidden bg-[#09090d]">
          {children}
        </main>
      </div>
    </WorkspaceProvider>
  );
}
