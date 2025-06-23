"use client"
import { useAuth } from "@/contexts/auth-provider";
import { useRouter } from "next/navigation";
import { useEffect } from "react";
import { SidebarProvider } from "@/components/ui/sidebar";
import { GroupSidebar } from "@/components/group/group-sidebar";
import { Skeleton } from "@/components/ui/skeleton";

export default function AppLayout({ children }: { children: React.ReactNode }) {
  const { isAuthenticated, isLoading, logout } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isLoading, isAuthenticated, router]);

  if (isLoading || !isAuthenticated) {
    return (
        <div className="flex h-screen w-full">
            <div className="w-64 bg-background border-r p-4">
                <Skeleton className="h-8 w-3/4 mb-6"/>
                <div className="space-y-2">
                    <Skeleton className="h-8 w-full"/>
                    <Skeleton className="h-8 w-full"/>
                    <Skeleton className="h-8 w-full"/>
                </div>
            </div>
            <div className="flex-1 p-4">
                <Skeleton className="h-full w-full"/>
            </div>
        </div>
    );
  }

  return (
    <SidebarProvider>
        <div className="flex h-screen w-full bg-muted/40">
            <GroupSidebar onLogout={logout} />
            <main className="flex-1 flex flex-col h-screen">
                {children}
            </main>
        </div>
    </SidebarProvider>
  );
}
