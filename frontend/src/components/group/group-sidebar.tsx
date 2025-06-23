"use client";

import { useEffect, useState } from 'react';
import { useRouter, useParams } from 'next/navigation';
import { BrainCircuit, PlusCircle, LogOut, Loader2, Users } from 'lucide-react';
import { Sidebar, SidebarHeader, SidebarContent, SidebarMenu, SidebarMenuItem, SidebarMenuButton, SidebarFooter } from '@/components/ui/sidebar';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useAuth } from '@/contexts/auth-provider';
import { fetchWithAuth } from '@/lib/api';
import type { GroupRead } from '@/types';
import { useToast } from '@/hooks/use-toast';
import { GroupCreateModal } from './group-create-modal';

interface GroupSidebarProps {
  onLogout: () => void;
}

export function GroupSidebar({ onLogout }: GroupSidebarProps) {
  const { user } = useAuth();
  const router = useRouter();
  const params = useParams();
  const { toast } = useToast();

  const [groups, setGroups] = useState<GroupRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isModalOpen, setIsModalOpen] = useState(false);

  useEffect(() => {
    const fetchGroups = async () => {
      setIsLoading(true);
      try {
        const data = await fetchWithAuth('/groups/');
        setGroups(data);
      } catch (error) {
        toast({
          variant: 'destructive',
          title: 'Failed to fetch groups',
          description: 'Please try again later.',
        });
      } finally {
        setIsLoading(false);
      }
    };
    if (user) {
      fetchGroups();
    }
  }, [user, toast]);

  const handleGroupCreated = (newGroup: GroupRead) => {
    setGroups(prev => [...prev, newGroup]);
    router.push(`/groups/${newGroup.id}`);
  };

  return (
    <>
      <Sidebar className="border-r" side="left" variant="sidebar" collapsible="icon">
        <SidebarHeader className="p-4 justify-start">
            <div className="flex items-center gap-2 w-full">
                <BrainCircuit className="h-7 w-7 text-primary" />
                <span className="font-semibold text-lg text-primary font-headline group-data-[collapsible=icon]:hidden">SynapseUI</span>
            </div>
        </SidebarHeader>
        <SidebarContent className="p-2">
            <div className="flex justify-between items-center mb-2 px-2">
                <p className="text-sm font-semibold text-muted-foreground group-data-[collapsible=icon]:hidden">Groups</p>
                <Button variant="ghost" size="icon" className="h-7 w-7 group-data-[collapsible=icon]:mx-auto" onClick={() => setIsModalOpen(true)}>
                    <PlusCircle className="h-5 w-5"/>
                </Button>
            </div>
          <SidebarMenu>
            {isLoading ? (
              Array.from({ length: 3 }).map((_, i) => (
                <SidebarMenuItem key={i}>
                  <Skeleton className="h-8 w-full" />
                </SidebarMenuItem>
              ))
            ) : (
              groups.map((group) => (
                <SidebarMenuItem key={group.id}>
                  <SidebarMenuButton
                    onClick={() => router.push(`/groups/${group.id}`)}
                    isActive={params.groupId === group.id}
                    className="justify-start"
                    tooltip={group.name}
                  >
                    <Users/>
                    <span>{group.name}</span>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))
            )}
          </SidebarMenu>
        </SidebarContent>
        <SidebarFooter className="p-4 border-t">
          <Button variant="ghost" className="w-full justify-start gap-2" onClick={onLogout}>
            <LogOut className="h-5 w-5" />
            <span className="group-data-[collapsible=icon]:hidden">Logout</span>
          </Button>
        </SidebarFooter>
      </Sidebar>
      <GroupCreateModal 
        isOpen={isModalOpen} 
        onOpenChange={setIsModalOpen} 
        onGroupCreated={handleGroupCreated} 
      />
    </>
  );
}
