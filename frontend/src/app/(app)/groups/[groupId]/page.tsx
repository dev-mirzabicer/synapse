"use client";

import React, { useState, useEffect, useCallback } from "react";
import { fetchWithAuth } from "@/lib/api";
import type { GroupDetailRead } from "@/types";
import { ChatView } from "@/components/chat/chat-view";
import { AgentPanel } from "@/components/chat/agent-panel";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";

export default function GroupChatPage({ params }: { params: { groupId: string } }) {
  const { groupId } = params;
  const { toast } = useToast();
  const [group, setGroup] = useState<GroupDetailRead | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  const fetchGroupDetails = useCallback(async () => {
    setIsLoading(true);
    try {
      const data = await fetchWithAuth(`/groups/${groupId}`);
      setGroup(data);
    } catch (error) {
      toast({
        variant: "destructive",
        title: "Failed to load group",
        description: "Could not fetch details for this group.",
      });
      setGroup(null);
    } finally {
      setIsLoading(false);
    }
  }, [groupId, toast]);

  useEffect(() => {
    if (groupId) {
      fetchGroupDetails();
    }
  }, [groupId, fetchGroupDetails]);

  if (isLoading) {
    return (
      <div className="flex-1 flex h-full p-2 gap-2">
        <div className="flex-[3] bg-background rounded-lg border p-4 flex flex-col">
            <Skeleton className="h-full w-full"/>
        </div>
        <div className="flex-[1] bg-background rounded-lg border p-4">
            <Skeleton className="h-full w-full"/>
        </div>
      </div>
    );
  }

  if (!group) {
    return (
      <div className="flex h-full items-center justify-center bg-background rounded-lg m-2 border">
        <p>Could not load group data. Please select another group.</p>
      </div>
    );
  }

  return (
    <div className="flex-1 flex h-full p-2 gap-2 overflow-hidden">
      <div className="flex-[3] flex flex-col bg-background rounded-lg border">
        <ChatView group={group} />
      </div>
      <div className="flex-[1] bg-background rounded-lg border overflow-y-auto">
        <AgentPanel group={group} onAgentUpdate={fetchGroupDetails} />
      </div>
    </div>
  );
}
