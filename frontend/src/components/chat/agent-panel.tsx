"use client";

import { useState } from 'react';
import { GroupDetailRead, GroupMemberRead } from "@/types";
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ScrollArea } from '@/components/ui/scroll-area';
import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from '@/components/ui/accordion';
import { Bot, Cpu, Pencil, Trash2 } from 'lucide-react';

interface AgentPanelProps {
    group: GroupDetailRead;
    onAgentUpdate: () => void;
}

export function AgentPanel({ group, onAgentUpdate }: AgentPanelProps) {

    return (
        <div className="h-full flex flex-col">
            <div className="p-4 border-b">
                <h3 className="text-lg font-semibold">Agents</h3>
                <p className="text-sm text-muted-foreground">Members of this group</p>
            </div>
            <ScrollArea className="flex-1">
                <div className="p-4 space-y-4">
                    <Accordion type="multiple" className="w-full">
                        {group.members.map(member => (
                            <AccordionItem value={member.id} key={member.id}>
                                <AccordionTrigger>
                                    <div className='flex items-center gap-2'>
                                        {member.alias === 'Orchestrator' ? <Cpu className="h-5 w-5 text-primary"/> : <Bot className="h-5 w-5 text-accent-foreground"/>}
                                        <span className='font-semibold'>{member.alias}</span>
                                    </div>
                                </AccordionTrigger>
                                <AccordionContent>
                                    <div className='space-y-3 text-sm p-2 bg-muted/50 rounded-md'>
                                        <div>
                                            <h4 className='font-semibold text-muted-foreground'>Role</h4>
                                            <p className='font-mono text-xs p-2 bg-background rounded'>{member.system_prompt}</p>
                                        </div>
                                         <div>
                                            <h4 className='font-semibold text-muted-foreground'>Model</h4>
                                            <p>{member.provider}/{member.model} (t={member.temperature})</p>
                                        </div>
                                        {member.tools && member.tools.length > 0 && (
                                            <div>
                                                <h4 className='font-semibold text-muted-foreground'>Tools</h4>
                                                <div className='flex flex-wrap gap-1 mt-1'>
                                                    {member.tools.map(tool => (
                                                        <span key={tool} className='text-xs bg-accent text-accent-foreground rounded-full px-2 py-0.5'>{tool}</span>
                                                    ))}
                                                </div>
                                            </div>
                                        )}
                                        {member.alias !== 'Orchestrator' && (
                                            <div className='flex gap-2 pt-2'>
                                                 <Button variant="outline" size="sm" disabled>
                                                    <Pencil className='h-3 w-3 mr-1'/> Edit
                                                 </Button>
                                                  <Button variant="destructive" size="sm" disabled>
                                                    <Trash2 className='h-3 w-3 mr-1'/> Delete
                                                 </Button>
                                            </div>
                                        )}
                                    </div>
                                </AccordionContent>
                            </AccordionItem>
                        ))}
                    </Accordion>
                </div>
            </ScrollArea>
        </div>
    )
}
