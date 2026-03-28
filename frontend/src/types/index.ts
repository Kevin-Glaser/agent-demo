export interface ChatMessage {
  role: 'user' | 'assistant' | 'system';
  content: string;
}

export interface ChatRequest {
  message: string;
  history: ChatMessage[];
}

export interface CallToolResult {
  name: string;
  result: string | null;
  error: string | null;
  call_tool_id: string;
}

export interface ChatResponse {
  response: string | null;
  callTools: CallToolResult[];
}

export interface MCPTool {
  name: string;
  description?: string;
  inputSchema?: Record<string, unknown>;
}

export interface SkillMetadata {
  name: string;
  description: string;
  license?: string;
  compatibility?: string;
  metadata?: {
    author?: string;
    version?: string;
  };
}