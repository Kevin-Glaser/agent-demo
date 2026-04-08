import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, CheckCircle2, XCircle, Undo2, Trash2 } from 'lucide-react';
import type { ChatMessage, CallToolResult } from '@/types';
import { chatStream, parseSSEStream, rollback, deleteTurn } from '@/api';

interface ChatProps {
  initialMessage?: string;
}

export function Chat({ initialMessage }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: initialMessage || '你好！有什么可以帮你的吗？' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const [toolResults, setToolResults] = useState<CallToolResult[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, toolResults]);

  // Handle streaming chat
  const handleStreamingSubmit = async (userMessage: string) => {
    // Abort any existing stream
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    const history = messages.map(m => ({ role: m.role, content: m.content }));
    setStreamingContent('');
    setToolResults([]);

    try {
      const response = await chatStream({ message: userMessage, history });

      // Add placeholder message that will be updated
      setMessages(prev => [...prev, { role: 'assistant', content: '' }]);

      let fullContent = '';
      const toolCallsMap = new Map<string, CallToolResult>();

      for await (const chunk of parseSSEStream(response)) {
        if (abortControllerRef.current?.signal.aborted) break;

        switch (chunk.chunk_type) {
          case 'text-delta':
            if (chunk.delta) {
              fullContent += chunk.delta;
              setStreamingContent(fullContent);
              // Update the last message with streaming content
              setMessages(prev => {
                const updated = [...prev];
                if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
                  updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullContent };
                }
                return updated;
              });
            }
            break;

          case 'reasoning-delta':
            // Could display reasoning separately if needed
            break;

          case 'tool-call':
            if (chunk.tool_call_id && chunk.tool_name) {
              toolCallsMap.set(chunk.tool_call_id, {
                name: chunk.tool_name,
                result: null,
                error: null,
                call_tool_id: chunk.tool_call_id,
              });
            }
            break;

          case 'tool-result':
            if (chunk.tool_call_id) {
              const existing = toolCallsMap.get(chunk.tool_call_id);
              if (existing) {
                existing.result = chunk.content;
              }
            }
            break;

          case 'done':
            // Stream completed
            break;

          case 'error':
            if (chunk.content) {
              fullContent += `\n[错误: ${chunk.content}]`;
              setMessages(prev => {
                const updated = [...prev];
                if (updated.length > 0 && updated[updated.length - 1].role === 'assistant') {
                  updated[updated.length - 1] = { ...updated[updated.length - 1], content: fullContent };
                }
                return updated;
              });
            }
            break;
        }
      }

      // Update tool results
      if (toolCallsMap.size > 0) {
        setToolResults(Array.from(toolCallsMap.values()));
      }
    } catch (error) {
      if (error instanceof Error && error.name !== 'AbortError') {
        setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，发生错误，请稍后重试。' }]);
      }
    } finally {
      setStreamingContent('');
      abortControllerRef.current = null;
      setLoading(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);

    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    // Use streaming by default
    await handleStreamingSubmit(userMessage);
  };

  const handleStop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      setLoading(false);
      setStreamingContent('');
    }
  };

  const handleRollback = async (messageIndex: number) => {
    try {
      const result = await rollback(1, messageIndex);
      if (result.messages_removed > 0) {
        // Remove messages from messageIndex onwards
        setMessages(prev => prev.slice(0, messageIndex));
      }
    } catch (error) {
      console.error('Rollback failed:', error);
    }
  };

  const handleDeleteTurn = async (messageIndex: number) => {
    try {
      const result = await deleteTurn(messageIndex);
      if (result.removed > 0) {
        // Update local state to remove the deleted messages
        // We need to remove 'result.removed' messages starting from messageIndex
        setMessages(prev => [
          ...prev.slice(0, messageIndex),
          ...prev.slice(messageIndex + result.removed)
        ]);
      }
    } catch (error) {
      console.error('Delete turn failed:', error);
    }
  };

  return (
    <div className="flex flex-col h-full">
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((message, index) => (
          <div key={index} className={`flex gap-3 ${message.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {message.role === 'assistant' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--primary))] flex items-center justify-center">
                <Bot className="w-5 h-5 text-[hsl(var(--primary-foreground))]" />
              </div>
            )}
            <div
              className={`max-w-[70%] rounded-2xl px-4 py-3 ${
                message.role === 'user'
                  ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
                  : 'bg-[hsl(var(--card))] text-[hsl(var(--card-foreground))]'
              }`}
            >
              <p className="whitespace-pre-wrap">{message.content}</p>
              {index === messages.length - 1 && streamingContent && message.role === 'assistant' && (
                <span className="animate-pulse">▊</span>
              )}
            </div>
            {message.role === 'user' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--secondary))] flex items-center justify-center">
                <User className="w-5 h-5 text-[hsl(var(--secondary-foreground))]" />
              </div>
            )}

            {message.role === 'user' && index > 0 && (
              <>
                <button
                  onClick={() => handleRollback(index)}
                  className="flex-shrink-0 p-1 hover:bg-[hsl(var(--muted))] rounded-full transition-colors"
                  title="回退此消息"
                >
                  <Undo2 className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                </button>
                <button
                  onClick={() => handleDeleteTurn(index)}
                  className="flex-shrink-0 p-1 hover:bg-[hsl(var(--muted))] rounded-full transition-colors"
                  title="删除此轮对话"
                >
                  <Trash2 className="w-4 h-4 text-[hsl(var(--muted-foreground))]" />
                </button>
              </>
            )}
          </div>
        ))}

        {loading && !streamingContent && (
          <div className="flex gap-3 justify-start">
            <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--primary))] flex items-center justify-center">
              <Bot className="w-5 h-5 text-[hsl(var(--primary-foreground))]" />
            </div>
            <div className="bg-[hsl(var(--card))] rounded-2xl px-4 py-3">
              <Loader2 className="w-5 h-5 animate-spin text-[hsl(var(--primary))]" />
            </div>
          </div>
        )}

        {toolResults.length > 0 && (
          <div className="flex gap-3 justify-start ml-11">
            <div className="bg-[hsl(var(--muted))] border border-[hsl(var(--border))] rounded-lg p-3 w-full max-w-md">
              <p className="text-sm font-medium text-[hsl(var(--foreground))] mb-2">工具调用结果:</p>
              <div className="space-y-2">
                {toolResults.map((tool, index) => (
                  <div key={index} className="flex items-start gap-2 text-sm">
                    {tool.error ? (
                      <XCircle className="w-4 h-4 text-red-500 flex-shrink-0 mt-0.5" />
                    ) : (
                      <CheckCircle2 className="w-4 h-4 text-green-500 flex-shrink-0 mt-0.5" />
                    )}
                    <div>
                      <span className="font-medium">{tool.name}:</span>
                      <span className="ml-1">{tool.error || tool.result}</span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
        <div ref={messagesEndRef} />
      </div>

      <form onSubmit={handleSubmit} className="p-4 border-t border-[hsl(var(--border))]">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="输入你的消息..."
            className="flex-1 bg-[hsl(var(--input))] border border-[hsl(var(--border))] rounded-full px-4 py-3 text-[hsl(var(--foreground))] placeholder-[hsl(var(--muted-foreground))] focus:outline-none focus:ring-2 focus:ring-[hsl(var(--ring))]"
            disabled={loading}
          />
          {loading && streamingContent ? (
            <button
              type="button"
              onClick={handleStop}
              className="bg-[hsl(var(--destructive))] hover:bg-[hsl(var(--destructive))]/90 text-[hsl(var(--destructive-foreground))] rounded-full p-3 transition-colors"
            >
              <XCircle className="w-5 h-5" />
            </button>
          ) : (
            <button
              type="submit"
              disabled={loading || !input.trim()}
              className="bg-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/90 disabled:opacity-50 disabled:cursor-not-allowed text-[hsl(var(--primary-foreground))] rounded-full p-3 transition-colors"
            >
              <Send className="w-5 h-5" />
            </button>
          )}
        </div>
      </form>
    </div>
  );
}
