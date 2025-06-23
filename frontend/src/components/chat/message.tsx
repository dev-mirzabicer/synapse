"use client";

import { MessageHistoryRead } from "@/types";
import { cn } from "@/lib/utils";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { User, Bot, Cpu, Wrench } from "lucide-react";
import { format } from 'date-fns';
import { Card, CardContent, CardHeader, CardTitle } from "../ui/card";

interface MessageProps {
  message: MessageHistoryRead;
}

const SenderAvatar = ({ alias }: { alias: string }) => {
    const isUser = alias === "User";
    const isOrchestrator = alias === "Orchestrator";
    const isTool = !isUser && !isOrchestrator && !/^[A-Z]/.test(alias);

    const getIcon = () => {
        if(isUser) return <User className="h-5 w-5"/>;
        if(isOrchestrator) return <Cpu className="h-5 w-5"/>;
        if(isTool) return <Wrench className="h-5 w-5"/>;
        return <Bot className="h-5 w-5"/>;
    }

    const getInitials = () => {
        if (isUser) return "U";
        if (isTool) return alias.substring(0, 1).toUpperCase();
        return alias.substring(0, 2).toUpperCase();
    }
    
    return (
        <Avatar className="h-8 w-8">
            <AvatarFallback className={cn(
                isUser ? "bg-primary text-primary-foreground" : "bg-secondary text-secondary-foreground"
            )}>
                {getIcon()}
            </AvatarFallback>
        </Avatar>
    )
};

const ToolCall = ({ toolCall }: { toolCall: any }) => (
    <Card className="mt-2 bg-muted/50">
        <CardHeader className="p-2">
            <CardTitle className="text-sm flex items-center gap-2">
                <Wrench className="h-4 w-4 text-muted-foreground"/>
                Using tool: <span className="font-mono text-accent">{toolCall.name}</span>
            </CardTitle>
        </CardHeader>
        <CardContent className="p-2 pt-0">
            <pre className="text-xs bg-background p-2 rounded-md font-code overflow-x-auto">
                {JSON.stringify(toolCall.args, null, 2)}
            </pre>
        </CardContent>
    </Card>
);

export function Message({ message }: MessageProps) {
  const isUser = message.sender_alias === "User";
  const toolCalls = message.meta?.kwargs?.tool_calls;

  return (
    <div className={cn("flex items-start gap-3", isUser && "justify-end")}>
      {!isUser && <SenderAvatar alias={message.sender_alias} />}
      <div
        className={cn(
          "max-w-xl rounded-lg p-3",
          isUser
            ? "bg-primary text-primary-foreground"
            : "bg-card border"
        )}
      >
        <div className="flex items-center gap-2 mb-1">
          {!isUser && <p className="text-sm font-semibold">{message.sender_alias}</p>}
          <time className={cn("text-xs", isUser ? "text-primary-foreground/70" : "text-muted-foreground")}>
            {format(new Date(message.timestamp), 'HH:mm')}
          </time>
        </div>
        <p className="whitespace-pre-wrap text-sm">{message.content}</p>
        {toolCalls && Array.isArray(toolCalls) && toolCalls.map((tc: any) => (
            <ToolCall key={tc.id} toolCall={tc}/>
        ))}
      </div>
      {isUser && <SenderAvatar alias={message.sender_alias} />}
    </div>
  );
}
