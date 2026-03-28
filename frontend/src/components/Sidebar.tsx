import { useState, useEffect } from 'react';
import { Bot, Wrench, Package, Trash2, Upload, RefreshCw, Loader2 } from 'lucide-react';
import { getTools, getSkills, uploadSkill, deleteSkill } from '@/api';
import type { MCPTool, SkillMetadata } from '@/types';

interface SidebarProps {
  activeTab: 'chat' | 'tools' | 'skills';
  onTabChange: (tab: 'chat' | 'tools' | 'skills') => void;
}

export function Sidebar({ activeTab, onTabChange }: SidebarProps) {
  return (
    <div className="w-16 hover:w-56 bg-[hsl(var(--card))] border-r border-[hsl(var(--border))] transition-all duration-300 overflow-hidden flex flex-col py-4 group">
      <div className="flex items-center gap-3 px-4 mb-6">
        <div className="w-8 h-8 rounded-lg bg-[hsl(var(--primary))] flex items-center justify-center flex-shrink-0">
          <Bot className="w-5 h-5 text-[hsl(var(--primary-foreground))]" />
        </div>
        <span className="font-semibold text-[hsl(var(--foreground))] whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">
          Agent Demo
        </span>
      </div>

      <nav className="flex-1 space-y-1 px-2">
        <NavItem
          icon={<Bot className="w-5 h-5" />}
          label="聊天"
          active={activeTab === 'chat'}
          onClick={() => onTabChange('chat')}
        />
        <NavItem
          icon={<Wrench className="w-5 h-5" />}
          label="工具"
          active={activeTab === 'tools'}
          onClick={() => onTabChange('tools')}
        />
        <NavItem
          icon={<Package className="w-5 h-5" />}
          label="技能"
          active={activeTab === 'skills'}
          onClick={() => onTabChange('skills')}
        />
      </nav>
    </div>
  );
}

function NavItem({
  icon,
  label,
  active,
  onClick,
}: {
  icon: React.ReactNode;
  label: string;
  active: boolean;
  onClick: () => void;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-3 w-full px-3 py-2.5 rounded-lg transition-colors ${
        active
          ? 'bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))]'
          : 'text-[hsl(var(--muted-foreground))] hover:bg-[hsl(var(--muted))] hover:text-[hsl(var(--foreground))]'
      }`}
    >
      <span className="flex-shrink-0">{icon}</span>
      <span className="whitespace-nowrap opacity-0 group-hover:opacity-100 transition-opacity">{label}</span>
    </button>
  );
}

export function ToolsPanel() {
  const [tools, setTools] = useState<MCPTool[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTools = async (reload: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getTools(reload);
      setTools(data);
    } catch {
      setError('加载工具失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTools(true);
  }, []);

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-[hsl(var(--foreground))]">MCP 工具</h2>
        <button
          onClick={() => fetchTools(true)}
          className="p-2 rounded-lg hover:bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] transition-colors"
        >
          <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
        </button>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4 mb-4">
          <p className="text-red-500 text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
        </div>
      ) : tools.length === 0 ? (
        <div className="text-center py-12 text-[hsl(var(--muted-foreground))]">
          <Wrench className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>暂无工具</p>
          <p className="text-sm mt-1">请配置并启动 MCP 服务器</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {tools.map((tool, index) => (
            <div
              key={index}
              className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4"
            >
              <h3 className="font-medium text-[hsl(var(--foreground))] mb-1">{tool.name}</h3>
              {tool.description && (
                <p className="text-sm text-[hsl(var(--muted-foreground))]">{tool.description}</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function SkillsPanel() {
  const [skills, setSkills] = useState<SkillMetadata[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);

  const fetchSkills = async () => {
    setError(null);
    try {
      const data = await getSkills();
      setSkills(data);
    } catch (err) {
      console.error('Failed to fetch skills:', err);
      setError(err instanceof Error ? err.message : '加载技能失败');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSkills();
  }, []);

  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    setUploading(true);
    setError(null);
    try {
      await uploadSkill(file);
      await fetchSkills();
    } catch (err) {
      console.error('Upload error:', err);
      setError(err instanceof Error ? err.message : '上传技能失败');
    } finally {
      setUploading(false);
    }
  };

  const handleDelete = async (skillName: string) => {
    if (!confirm(`确定要删除技能 "${skillName}" 吗？`)) return;

    try {
      await deleteSkill(skillName);
      await fetchSkills();
    } catch {
      setError('删除技能失败');
    }
  };

  return (
    <div className="p-6">
      <div className="flex items-center justify-between mb-6">
        <h2 className="text-xl font-semibold text-[hsl(var(--foreground))]">技能管理</h2>
        <div className="flex gap-2">
          <button
            onClick={fetchSkills}
            className="p-2 rounded-lg hover:bg-[hsl(var(--muted))] text-[hsl(var(--muted-foreground))] transition-colors"
          >
            <RefreshCw className={`w-5 h-5 ${loading ? 'animate-spin' : ''}`} />
          </button>
          <label className="cursor-pointer">
            <input type="file" accept=".zip" onChange={handleUpload} className="hidden" disabled={uploading} />
            <div className="flex items-center gap-2 px-3 py-2 bg-[hsl(var(--primary))] hover:bg-[hsl(var(--primary))]/90 text-[hsl(var(--primary-foreground))] rounded-lg transition-colors">
              {uploading ? (
                <Loader2 className="w-5 h-5 animate-spin" />
              ) : (
                <Upload className="w-5 h-5" />
              )}
              <span className="text-sm font-medium">上传</span>
            </div>
          </label>
        </div>
      </div>

      {error && (
        <div className="bg-red-500/10 border border-red-500/50 rounded-lg p-4 mb-4">
          <p className="text-red-500 text-sm">{error}</p>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-[hsl(var(--primary))]" />
        </div>
      ) : skills.length === 0 ? (
        <div className="text-center py-12 text-[hsl(var(--muted-foreground))]">
          <Package className="w-12 h-12 mx-auto mb-4 opacity-50" />
          <p>暂无技能</p>
          <p className="text-sm mt-1">上传 .zip 格式的技能包</p>
        </div>
      ) : (
        <div className="grid gap-4">
          {skills.map((skill, index) => (
            <div
              key={index}
              className="bg-[hsl(var(--card))] border border-[hsl(var(--border))] rounded-lg p-4 flex items-start justify-between"
            >
              <div>
                <h3 className="font-medium text-[hsl(var(--foreground))] mb-1">{skill.name}</h3>
                <p className="text-sm text-[hsl(var(--muted-foreground))]">{skill.description}</p>
                {skill.metadata && (
                  <div className="flex gap-4 mt-2 text-xs text-[hsl(var(--muted-foreground))]">
                    {skill.metadata.author && <span>作者: {skill.metadata.author}</span>}
                    {skill.metadata.version && <span>版本: {skill.metadata.version}</span>}
                  </div>
                )}
              </div>
              <button
                onClick={() => handleDelete(skill.name)}
                className="p-2 rounded-lg hover:bg-red-500/10 text-red-500 transition-colors"
              >
                <Trash2 className="w-4 h-4" />
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}