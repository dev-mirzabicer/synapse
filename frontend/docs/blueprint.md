# **App Name**: SynapseUI

## Core Features:

- Authentication: User authentication via login and registration, with JWT storage in local storage.
- Group Listing and Selection: Display a list of chat groups owned by the user and allow the user to select them.
- Group Creation: Creation of new chat groups with a name and agents with configurable parameters (alias, role prompt, tools, LLM provider, model, temperature).
- Agent Management: Display of agents (members) within a selected group with the possibility to edit or delete them, including their alias, role prompt, associated tools, LLM provider, model, and temperature.
- Real-Time Chat Display: Real-time display of messages in a chat interface, handling different sender aliases (User, Orchestrator, Agents, Tools) and rendering of tool calls and results.
- Message Sending: Send user messages to a selected group, displaying immediate acknowledgement and processing state.
- Smart Scrollback: Smart Scrollback: When new data is loaded, automatically use a tool to find the messages most relevant to the current conversation and focus them.

## Style Guidelines:

- Primary color: Deep Indigo (#4B0082) to represent intelligence and sophistication.
- Background color: Light Gray (#F0F0F0) to provide a clean, modern backdrop.
- Accent color: Teal (#008080) to highlight interactive elements and important information, standing out from the primary color.
- Body font: 'Inter', a sans-serif font providing a modern and objective feel; suited for both headlines and body text
- Code font: 'Source Code Pro' for displaying code snippets in a clear and readable manner.
- Use minimalist, professional icons representing different actions and entities (e.g., users, agents, tools) within the interface.
- Employ a modular layout with clear divisions between chat groups, agents, and the chat interface for intuitive navigation.
- Implement subtle animations to indicate loading states and provide feedback for user interactions, improving overall engagement.