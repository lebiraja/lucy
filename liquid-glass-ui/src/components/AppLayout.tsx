import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import AuroraBackground from "@/components/AuroraBackground";
import { Outlet, useLocation } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";

export default function AppLayout() {
  const location = useLocation();
  const isChat = location.pathname.startsWith("/chat");
  const { data: health } = useQuery({
    queryKey: ["health"],
    queryFn: api.getHealth,
    refetchInterval: 10000,
  });

  return (
    <SidebarProvider>
      <div className="min-h-screen flex w-full relative">
        <AuroraBackground />
        <AppSidebar />
        <div className="flex-1 flex flex-col min-w-0">
          <header className="h-14 flex items-center justify-between px-4 border-b border-border/50">
            <SidebarTrigger className="text-muted-foreground hover:text-foreground transition-colors" />
            <div className="flex items-center gap-3">
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="status-dot-online" />
                <span>{health?.online_agents ?? 0}/{health?.total_agents ?? 0} agents</span>
              </div>
              <div className="w-px h-4 bg-border" />
              <div className="text-xs text-muted-foreground">
                {health?.success_rate ?? 0}% success
              </div>
            </div>
          </header>
          <main className={`flex-1 overflow-hidden ${isChat ? "" : "overflow-auto p-6"}`}>
            <Outlet />
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
