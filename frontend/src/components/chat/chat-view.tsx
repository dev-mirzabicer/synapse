"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { useWebSocket } from "@/hooks/use-websocket";
import type { GroupDetailRead, MessageHistoryRead } from "@/types";
import { fetchWithAuth } from "@/lib/api";
import { MessageInput } from "./message-input";
import { Message } from "./message";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import { useToast } from "@/hooks/use-toast";
import { smartScrollback } from "@/ai/flows/smart-scrollback";
import { Button } from "../ui/button";

export function ChatView({ group }: { group: GroupDetailRead }) {
  const { toast } = useToast();
  const { lastMessage, isConnected, error: wsError } = useWebSocket(group.id);
  const [messages, setMessages] = useState<MessageHistoryRead[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isTurnActive, setIsTurnActive] = useState(false);
  const [isHistoryLoading, setIsHistoryLoading] = useState(false);
  const [canLoadMore, setCanLoadMore] = useState(true);
  
  const messageRefs = useRef<Map<string, HTMLDivElement>>(new Map());
  const scrollAreaRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (wsError) {
      toast({
        variant: "destructive",
        title: "WebSocket Error",
        description: "Connection to the server was lost. Please refresh.",
      });
    }
  }, [wsError, toast]);

  const fetchHistory = useCallback(async (beforeTimestamp?: string) => {
    if (!canLoadMore && !beforeTimestamp) return;
    setIsHistoryLoading(true);
    try {
      const endpoint = beforeTimestamp ? `/groups/${group.id}/messages?limit=50&before_timestamp=${beforeTimestamp}` : `/groups/${group.id}/messages?limit=50`;
      const history = await fetchWithAuth(endpoint);
      
      if (history.length < 50) {
        setCanLoadMore(false);
      }

      const currentConversation = messages.slice(-10).map(m => `${m.sender_alias}: ${m.content}`).join('\n');
      const messagesToAnalyze = history.map((m: MessageHistoryRead) => `${m.id}::${m.sender_alias}: ${m.content}`);

      let relevantId: string | undefined;
      if (messages.length > 0 && history.length > 0) {
        try {
          const result = await smartScrollback({ messages: messagesToAnalyze, currentConversation });
          relevantId = result.relevantMessageIds?.[0];
        } catch (aiError) {
          console.error("Smart scrollback failed:", aiError);
        }
      }
      
      setMessages(prev => [...history, ...prev]);

      if (relevantId) {
        setTimeout(() => {
           const element = messageRefs.current.get(relevantId!);
           element?.scrollIntoView({ behavior: 'smooth', block: 'center' });
           element?.classList.add('bg-primary/10', 'transition-all', 'duration-1000');
           setTimeout(() => element?.classList.remove('bg-primary/10'), 2000);
        }, 100);
      } else if(!beforeTimestamp) {
        setTimeout(() => {
          scrollAreaRef.current?.scrollTo({ top: scrollAreaRef.current.scrollHeight, behavior: 'smooth' });
        }, 100);
      }

    } catch (error) {
      toast({ variant: "destructive", title: "Failed to fetch message history." });
    } finally {
      setIsLoading(false);
      setIsHistoryLoading(false);
    }
  }, [group.id, toast, messages, canLoadMore]);


  useEffect(() => {
    setIsLoading(true);
    setMessages([]);
    setCanLoadMore(true);
    fetchHistory();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [group.id]);

  useEffect(() => {
    if (lastMessage) {
      if (lastMessage.sender_alias === 'User') {
        setIsTurnActive(true);
      }
      if (lastMessage.sender_alias === 'Orchestrator' && lastMessage.content.includes('TASK_COMPLETE')) {
        setIsTurnActive(false);
      }
      setMessages((prev) => [...prev, lastMessage]);
      setTimeout(() => {
        scrollAreaRef.current?.scrollTo({ top: scrollAreaRef.current.scrollHeight, behavior: 'smooth' });
      }, 100);
    }
  }, [lastMessage]);

  const handleLoadMore = () => {
    if (messages.length > 0) {
        fetchHistory(messages[0].timestamp);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="p-4 border-b">
        <h2 className="text-xl font-semibold">{group.name}</h2>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span className={`h-2 w-2 rounded-full ${isConnected ? 'bg-green-500' : 'bg-red-500'}`}></span>
            {isConnected ? "Connected" : "Disconnected"}
        </div>
      </div>
      <ScrollArea className="flex-1 p-4" ref={scrollAreaRef}>
        <div className="space-y-4">
          {isLoading ? (
            Array.from({ length: 5 }).map((_, i) => <Skeleton key={i} className="h-16 w-3/4 odd:ml-auto" />)
          ) : (
            <>
              {canLoadMore && (
                <div className="text-center">
                    <Button variant="outline" size="sm" onClick={handleLoadMore} disabled={isHistoryLoading}>
                        {isHistoryLoading ? 'Loading...' : 'Load older messages'}
                    </Button>
                </div>
              )}
              {messages.map((msg) => (
                <div key={msg.id} ref={el => el && messageRefs.current.set(msg.id, el)}>
                    <Message message={msg} />
                </div>
              ))}
            </>
          )}
        </div>
      </ScrollArea>
      <div className="p-4 border-t">
        <MessageInput groupId={group.id} disabled={isTurnActive || !isConnected} />
      </div>
    </div>
  );
}
