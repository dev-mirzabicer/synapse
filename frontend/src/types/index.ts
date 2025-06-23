// 6.1 User & Auth Schemas
export type UserCreate = {
  email: string;
  password: string;
};

export type Token = {
  access_token: string;
  token_type: "bearer";
};

export type UserRead = {
  id: string; // UUID
  email: string;
};

// 6.2 Group & Member Schemas
export type AgentConfigCreate = {
  alias: string;
  role_prompt: string;
  tools?: string[];
  provider?: string;
  model?: string;
  temperature?: number;
};

export type AgentConfigUpdate = Partial<AgentConfigCreate>;

export type GroupCreate = {
  name: string;
  members?: AgentConfigCreate[];
};

export type GroupUpdate = {
  name: string;
};

export type GroupRead = {
  id: string; // UUID
  name: string;
};

export type GroupMemberRead = {
  id: string; // UUID
  group_id: string; // UUID
  alias: string;
  system_prompt: string;
  tools: string[] | null;
  provider: string;
  model: string;
  temperature: number;
};

export type GroupDetailRead = {
  id: string; // UUID
  name: string;
  owner_id: string; // UUID
  created_at: string; // datetime
  updated_at: string; // datetime
  members: GroupMemberRead[];
};

// 6.3 Message Schemas
export type MessageCreate = {
  content: string;
};

export type MessageRead = {
  id: string; // UUID
  turn_id: string; // UUID
  sender_alias: "User";
  content: string;
};

export type MessageHistoryRead = {
  id: string; // UUID
  group_id: string; // UUID
  turn_id: string; // UUID
  sender_alias: string;
  content: string;
  timestamp: string; // datetime
  parent_message_id: string | null; // UUID
  meta: Record<string, any> | null;
};

// 6.4 System Schemas
export type ToolInfo = {
  name: string;
  description: string;
  args_schema: Record<string, any>; // JSON Schema
};

export type ModelInfo = {
  id: string;
  name: string;
};

export type ProviderInfo = {
  provider_name: string;
  models: ModelInfo[];
};
