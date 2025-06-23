"use client";

import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { Form, FormControl, FormField, FormItem } from "@/components/ui/form";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Send, Loader2 } from "lucide-react";
import { fetchWithAuth } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";
import { useState } from "react";

const messageSchema = z.object({
  content: z.string().min(1, "Message cannot be empty.").max(1000, "Message is too long."),
});

interface MessageInputProps {
  groupId: string;
  disabled?: boolean;
}

export function MessageInput({ groupId, disabled }: MessageInputProps) {
  const { toast } = useToast();
  const [isSending, setIsSending] = useState(false);

  const form = useForm<z.infer<typeof messageSchema>>({
    resolver: zodResolver(messageSchema),
    defaultValues: { content: "" },
  });

  const onSubmit = async (values: z.infer<typeof messageSchema>) => {
    setIsSending(true);
    try {
      await fetchWithAuth(`/groups/${groupId}/messages`, {
        method: "POST",
        body: JSON.stringify(values),
      });
      form.reset();
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "Failed to send message",
        description: error.message,
      });
    } finally {
        setIsSending(false);
    }
  };
  
  const handleKeyDown = (event: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        if(!disabled && !isSending && form.getValues('content').trim()) {
            form.handleSubmit(onSubmit)();
        }
    }
  }

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="flex items-start gap-2">
        <FormField
          control={form.control}
          name="content"
          render={({ field }) => (
            <FormItem className="flex-1">
              <FormControl>
                <Textarea
                  placeholder="Type your message..."
                  className="resize-none"
                  onKeyDown={handleKeyDown}
                  {...field}
                  disabled={disabled || isSending}
                />
              </FormControl>
            </FormItem>
          )}
        />
        <Button type="submit" size="icon" disabled={disabled || isSending}>
            {isSending ? <Loader2 className="h-4 w-4 animate-spin"/> : <Send className="h-4 w-4" />}
        </Button>
      </form>
    </Form>
  );
}
