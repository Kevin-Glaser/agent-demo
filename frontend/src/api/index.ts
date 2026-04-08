import type { ChatRequest, ChatResponse, MCPTool, SkillMetadata } from '@/types';

const API_BASE = '/api';

// SSE chunk types matching backend
export interface SSEChunk {
  chunk_type: string;
  content: string;
  delta?: string;
  tool_call_id?: string;
  tool_name?: string;
  tool_input?: string;
  tool_output?: string;
}

// Parse SSE stream from response
export async function* parseSSEStream(
  response: Response
): AsyncGenerator<SSEChunk, void, unknown> {
  const reader = response.body?.getReader();
  if (!reader) throw new Error('No response body');

  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim();
          if (data) {
            try {
              yield JSON.parse(data) as SSEChunk;
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

// Non-streaming chat
export async function chat(request: ChatRequest): Promise<ChatResponse> {
  const response = await fetch(`${API_BASE}/chat`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error('Chat request failed');
  return response.json();
}

// Streaming chat - returns SSE response
export async function chatStream(request: ChatRequest): Promise<Response> {
  const response = await fetch(`${API_BASE}/chat/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error('Chat stream request failed');
  return response;
}

// Streaming chat loop - returns SSE response for multi-turn conversations
export async function chatLoopStream(request: ChatRequest): Promise<Response> {
  const response = await fetch(`${API_BASE}/chat/loop`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) throw new Error('Chat loop stream request failed');
  return response;
}

export async function getTools(reload: boolean = false): Promise<MCPTool[]> {
  const url = reload ? `${API_BASE}/tools?reload=true` : `${API_BASE}/tools`;
  const response = await fetch(url);
  if (!response.ok) throw new Error('Failed to fetch tools');
  const data = await response.json();
  return data.tools;
}

export async function getSkills(): Promise<SkillMetadata[]> {
  const response = await fetch(`${API_BASE}/skills`);
  if (!response.ok) throw new Error('Failed to fetch skills');
  const data = await response.json();
  return data.skills;
}

export async function uploadSkill(file: File): Promise<{ success: boolean; skill?: { name: string; description: string } }> {
  const formData = new FormData();
  formData.append('file', file);
  const response = await fetch(`${API_BASE}/skills/upload`, {
    method: 'POST',
    body: formData,
  });
  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw new Error(data.detail || 'Failed to upload skill');
  }
  return response.json();
}

export async function deleteSkill(skillName: string): Promise<{ success: boolean }> {
  const response = await fetch(`${API_BASE}/skills/${skillName}`, {
    method: 'DELETE',
  });
  if (!response.ok) throw new Error('Failed to delete skill');
  return response.json();
}

export async function callTool(server: string, name: string, args: Record<string, unknown>): Promise<{ result: string }> {
  const response = await fetch(`${API_BASE}/call-tool`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ server, name, args }),
  });
  if (!response.ok) throw new Error('Failed to call tool');
  return response.json();
}

export interface RollbackResult {
  rolled_back: number;
  messages_removed: number;
  tokens_removed: number;
  remaining_messages: number;
}

export async function rollback(n_turns: number = 1, messageIndex?: number): Promise<RollbackResult> {
  const body: { n_turns: number; message_index?: number } = { n_turns };
  if (messageIndex !== undefined) {
    body.message_index = messageIndex;
  }
  const response = await fetch(`${API_BASE}/chat/rollback`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error('Rollback request failed');
  return response.json();
}

export interface DeleteTurnResult {
  removed: number;
  tokens_removed: number;
  remaining_messages: number;
}

export async function deleteTurn(messageIndex: number): Promise<DeleteTurnResult> {
  const response = await fetch(`${API_BASE}/chat/delete-turn`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message_index: messageIndex }),
  });
  if (!response.ok) throw new Error('Delete turn request failed');
  return response.json();
}

