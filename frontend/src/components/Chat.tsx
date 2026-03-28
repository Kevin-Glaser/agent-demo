import { useState, useRef, useEffect } from 'react';
import { Send, Bot, User, Loader2, CheckCircle2, XCircle } from 'lucide-react';
import type { ChatMessage, CallToolResult } from '@/types';
import { chat } from '@/api';

interface ChatProps {
  initialMessage?: string;
}

export function Chat({ initialMessage }: ChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    { role: 'assistant', content: initialMessage || '你好！有什么可以帮你的吗？' },
  ]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [toolResults, setToolResults] = useState<CallToolResult[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, toolResults]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || loading) return;

    const userMessage = input.trim();
    setInput('');
    setLoading(true);
    setToolResults([]);

    setMessages(prev => [...prev, { role: 'user', content: userMessage }]);

    const history = messages.map(m => ({ role: m.role, content: m.content }));

    try {
      const response = await chat({ message: userMessage, history });
      setMessages(prev => [...prev, { role: 'assistant', content: response.response || '' }]);
      if (response.callTools && response.callTools.length > 0) {
        setToolResults(response.callTools);
      }
    } catch {
      setMessages(prev => [...prev, { role: 'assistant', content: '抱歉，发生错误，请稍后重试。' }]);
    } finally {
      setLoading(false);
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
            </div>
            {message.role === 'user' && (
              <div className="flex-shrink-0 w-8 h-8 rounded-full bg-[hsl(var(--secondary))] flex items-center justify-center">
                <User className="w-5 h-5 text-[hsl(var(--secondary-foreground))]" />
              </div>
            )}
          </div>
        ))}

        {loading && (
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
          <button
            type="submit"
            disabled={loading || !input.trim()}
            className="bg-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/90 disabled:opacity-50 disabled:cursor-not-allowed text-[hsl(var(--primary-foreground))] rounded-full p-3 transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </form>
    </div>
  );
}