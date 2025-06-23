'use server';

/**
 * @fileOverview This file defines a Genkit flow for smart scrollback functionality.
 *
 * - smartScrollback - A function that takes a list of messages and the current conversation
 *   and returns a list of message IDs that are most relevant to the current conversation.
 * - SmartScrollbackInput - The input type for the smartScrollback function.
 * - SmartScrollbackOutput - The return type for the smartScrollback function.
 */

import {ai} from '@/ai/genkit';
import {z} from 'genkit';

const SmartScrollbackInputSchema = z.object({
  messages: z
    .array(z.string())
    .describe('The list of messages to analyze for relevance.'),
  currentConversation: z
    .string()
    .describe('The current conversation to find relevant messages to.'),
});
export type SmartScrollbackInput = z.infer<typeof SmartScrollbackInputSchema>;

const SmartScrollbackOutputSchema = z.object({
  relevantMessageIds: z
    .array(z.string())
    .describe('The list of message IDs that are most relevant to the current conversation.'),
});
export type SmartScrollbackOutput = z.infer<typeof SmartScrollbackOutputSchema>;

export async function smartScrollback(input: SmartScrollbackInput): Promise<SmartScrollbackOutput> {
  return smartScrollbackFlow(input);
}

const prompt = ai.definePrompt({
  name: 'smartScrollbackPrompt',
  input: {schema: SmartScrollbackInputSchema},
  output: {schema: SmartScrollbackOutputSchema},
  prompt: `You are an AI assistant that identifies relevant messages from a list of messages
based on their relevance to the current conversation.

Given the following list of messages:
{{#each messages}}{{{this}}}\n{{/each}}

And the current conversation:
{{currentConversation}}

Identify the messages that are most relevant to the current conversation and return their IDs.
Ensure that you only include IDs of messages that are actually in the provided list.

Return ONLY a JSON array of string IDs.
`,
});

const smartScrollbackFlow = ai.defineFlow(
  {
    name: 'smartScrollbackFlow',
    inputSchema: SmartScrollbackInputSchema,
    outputSchema: SmartScrollbackOutputSchema,
  },
  async input => {
    const {output} = await prompt(input);
    return output!;
  }
);
