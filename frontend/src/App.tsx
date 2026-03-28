import { useState } from 'react';
import { Chat } from '@/components/Chat';
import { Sidebar, ToolsPanel, SkillsPanel } from '@/components/Sidebar';

type Tab = 'chat' | 'tools' | 'skills';

function App() {
  const [activeTab, setActiveTab] = useState<Tab>('chat');

  return (
    <div className="flex h-screen bg-[hsl(var(--background))]">
      <Sidebar activeTab={activeTab} onTabChange={setActiveTab} />

      <main className="flex-1 flex flex-col overflow-hidden">
        <header className="h-14 border-b border-[hsl(var(--border))] bg-[hsl(var(--card))] flex items-center px-6">
          <h1 className="text-lg font-semibold text-[hsl(var(--foreground))]">
            {activeTab === 'chat' && 'AI 聊天'}
            {activeTab === 'tools' && 'MCP 工具'}
            {activeTab === 'skills' && '技能管理'}
          </h1>
        </header>

        <div className="flex-1 overflow-hidden">
          {activeTab === 'chat' && <Chat />}
          {activeTab === 'tools' && <ToolsPanel />}
          {activeTab === 'skills' && <SkillsPanel />}
        </div>
      </main>
    </div>
  );
}

export default App;