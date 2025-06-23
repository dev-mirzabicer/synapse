"use client";

import { useState, useEffect } from "react";
import { useForm, useFieldArray } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { fetchWithAuth } from "@/lib/api";
import type { GroupRead, ToolInfo, ProviderInfo, AgentConfigCreate } from "@/types";
import { useToast } from "@/hooks/use-toast";
import { Loader2, PlusCircle, Trash2 } from "lucide-react";
import { ScrollArea } from "../ui/scroll-area";
import { Separator } from "../ui/separator";

interface GroupCreateModalProps {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  onGroupCreated: (group: GroupRead) => void;
}

const agentConfigSchema = z.object({
  alias: z.string().min(1, "Alias is required.").max(100),
  role_prompt: z.string().min(1, "Role prompt is required."),
  tools: z.array(z.string()).optional(),
  provider: z.string().optional(),
  model: z.string().optional(),
  temperature: z.coerce.number().min(0).max(2).optional(),
});

const groupCreateSchema = z.object({
  name: z.string().min(1, "Group name is required.").max(100),
  members: z.array(agentConfigSchema).optional(),
});

export function GroupCreateModal({ isOpen, onOpenChange, onGroupCreated }: GroupCreateModalProps) {
  const { toast } = useToast();
  const [isLoading, setIsLoading] = useState(false);
  const [tools, setTools] = useState<ToolInfo[]>([]);
  const [llms, setLlms] = useState<ProviderInfo[]>([]);

  useEffect(() => {
    async function fetchSystemInfo() {
      try {
        const [toolsData, llmsData] = await Promise.all([
          fetchWithAuth("/system/tools"),
          fetchWithAuth("/system/llm-options"),
        ]);
        setTools(toolsData);
        setLlms(llmsData);
      } catch (error) {
        toast({
          variant: "destructive",
          title: "Failed to load system info",
          description: "Could not fetch available tools and LLMs.",
        });
      }
    }
    if (isOpen) {
      fetchSystemInfo();
    }
  }, [isOpen, toast]);

  const form = useForm<z.infer<typeof groupCreateSchema>>({
    resolver: zodResolver(groupCreateSchema),
    defaultValues: { name: "", members: [] },
  });

  const { fields, append, remove } = useFieldArray({
    control: form.control,
    name: "members",
  });

  const onSubmit = async (values: z.infer<typeof groupCreateSchema>) => {
    setIsLoading(true);
    try {
      const newGroup = await fetchWithAuth("/groups/", {
        method: "POST",
        body: JSON.stringify(values),
      });
      toast({ title: "Group created successfully!" });
      onGroupCreated(newGroup);
      onOpenChange(false);
      form.reset();
    } catch (error: any) {
      toast({
        variant: "destructive",
        title: "Failed to create group",
        description: error.message,
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <Dialog open={isOpen} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl">
        <DialogHeader>
          <DialogTitle>Create New Group</DialogTitle>
          <DialogDescription>
            Configure your new chat group and add initial agents.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
            <ScrollArea className="h-[60vh] p-1">
              <div className="p-4 space-y-6">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Group Name</FormLabel>
                      <FormControl>
                        <Input placeholder="My Research Team" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <Separator />

                <div>
                  <h3 className="text-lg font-medium mb-2">Agents</h3>
                  {fields.map((field, index) => (
                    <div key={field.id} className="p-4 border rounded-lg mb-4 space-y-4 relative">
                      <Button
                        type="button"
                        variant="ghost"
                        size="icon"
                        className="absolute top-2 right-2 h-7 w-7"
                        onClick={() => remove(index)}
                      >
                        <Trash2 className="h-4 w-4" />
                      </Button>
                      <FormField
                        control={form.control}
                        name={`members.${index}.alias`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Alias</FormLabel>
                            <FormControl>
                              <Input placeholder="WebResearcher" {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`members.${index}.role_prompt`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Role Prompt</FormLabel>
                            <FormControl>
                              <Textarea placeholder="Research diligently." {...field} />
                            </FormControl>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`members.${index}.provider`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>LLM Provider</FormLabel>
                            <Select onValueChange={field.onChange} defaultValue={field.value}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select a provider" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {llms.map((p) => <SelectItem key={p.provider_name} value={p.provider_name}>{p.provider_name}</SelectItem>)}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                      <FormField
                        control={form.control}
                        name={`members.${index}.model`}
                        render={({ field }) => (
                          <FormItem>
                            <FormLabel>Model</FormLabel>
                            <Select onValueChange={field.onChange} defaultValue={field.value} disabled={!form.watch(`members.${index}.provider`)}>
                              <FormControl>
                                <SelectTrigger>
                                  <SelectValue placeholder="Select a model" />
                                </SelectTrigger>
                              </FormControl>
                              <SelectContent>
                                {llms.find(p => p.provider_name === form.watch(`members.${index}.provider`))?.models.map(m => (
                                  <SelectItem key={m.id} value={m.id}>{m.name}</SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <FormMessage />
                          </FormItem>
                        )}
                      />
                    </div>
                  ))}

                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="mt-2"
                    onClick={() => append({ alias: "", role_prompt: "", provider: "gemini", model: "gemini-2.5-pro", temperature: 0.1 })}
                  >
                    <PlusCircle className="mr-2 h-4 w-4" />
                    Add Agent
                  </Button>
                </div>
              </div>
            </ScrollArea>
            <DialogFooter>
              <Button type="button" variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
              <Button type="submit" disabled={isLoading}>
                {isLoading && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Create Group
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}
