# Agent Demo 项目文档

## 项目概述

Agent Demo 是一个基于 FastAPI 构建的现代化 AI Agent 框架，支持 MCP 协议、Skills 系统以及更多扩展功能。项目采用前后端分离架构，前端使用 React + Vite，后端使用 FastAPI。

> 本文档详细说明项目结构和各文件作用，快速入门请参考 [README.md](README.md) 或 [README_CN.md](README_CN.md)

## 项目结构

```
agent-demo/
├── frontend/                      # React + Vite 前端
│   ├── src/
│   │   ├── api/                  # API 调用层
│   │   ├── components/            # React 组件
│   │   ├── types/                # TypeScript 类型定义
│   │   ├── App.tsx               # 主应用组件
│   │   ├── main.tsx              # 入口文件
│   │   └── index.css             # 全局样式（暗色主题）
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   └── ...
│
├── backend/                       # FastAPI 后端
│   ├── app/                       # 应用层
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI 主应用入口
│   │   └── api/                  # API 路由层
│   │       ├── __init__.py       # API 模块初始化，聚合所有路由
│   │       ├── chat.py           # 聊天接口 - 处理对话请求
│   │       ├── skills.py         # Skills 管理 API - 上传/删除/获取技能
│   │       └── tools.py          # MCP 工具 API - 获取/调用工具
│   │
│   ├── core/                      # 核心层
│   │   ├── __init__.py
│   │   ├── config.py             # 配置管理 - 环境变量和设置
│   │   └── exceptions.py         # 自定义异常类
│   │
│   ├── llm/                      # LLM 模块
│   │   ├── __init__.py
│   │   └── openai_service.py     # OpenAI 服务 - LLM 调用和工具执行
│   │
│   ├── mcp_client/               # MCP 客户端模块
│   │   ├── __init__.py
│   │   └── client.py             # MCP 客户端 - 连接和调用 MCP 服务器
│   │
│   ├── skills/                   # Skills 模块
│   │   ├── __init__.py
│   │   ├── manager.py            # Skill 管理器 - 管理技能生命周期
│   │   ├── loader.py             # Skill 加载器 - 多来源加载
│   │   ├── watcher.py            # Skill 文件监视器 - 热重载支持
│   │   └── parser.py             # SKILL.md 解析器 - 解析技能定义文件
│   │
│   ├── models/                   # 数据模型层
│   │   ├── __init__.py
│   │   ├── chat.py              # 聊天相关模型 - 请求/响应结构
│   │   ├── common.py            # 通用模型 - 工具调用请求等
│   │   ├── mcp.py               # MCP 相关模型 - 服务器配置/工具信息
│   │   └── skill.py             # Skill 相关模型 - 技能信息/元数据
│   │
│   ├── storage/                  # 存储层
│   │   └── skills/              # Skills 文件存储目录
│   │
│   ├── .env                     # 环境变量配置（不提交到 Git）
│   ├── .env.example             # 环境变量示例模板
│   ├── .python-version          # Python 版本指定
│   ├── mcp.json                 # MCP 服务器配置
│   ├── pyproject.toml           # 项目配置和依赖
│   └── uv.lock                  # 依赖锁定文件
│
├── README.md                      # 英文文档
├── README_CN.md                  # 中文文档
└── AGENTS.md                    # 本文档
```

## 快速开始

### 环境要求

- Python 3.12+
- Node.js 18+
- pnpm 包管理器
- uv 包管理器

### 安装步骤

#### 后端

1. **进入后端目录**
   ```bash
   cd backend
   ```

2. **创建虚拟环境**
   ```bash
   uv venv
   ```

3. **安装依赖**
   ```bash
   uv sync
   ```

4. **配置环境变量**
   ```bash
   cp .env.example .env
   # 编辑 .env 文件，填入必要的配置
   ```

#### 前端

1. **进入前端目录**
   ```bash
   cd frontend
   ```

2. **安装依赖**
   ```bash
   pnpm install
   ```

### 启动服务

1. **启动后端服务**（在 backend 目录）
   ```bash
   cd backend
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
   ```

2. **启动前端服务**（在 frontend 目录）
   ```bash
   cd frontend
   pnpm dev
   ```

前端运行在 http://localhost:5173，会自动代理 API 请求到后端 8002 端口。

### 注意事项

- 确保 `.env` 文件中已正确配置 `OPENAI_API_KEY` 等必要参数
- 如需使用 MCP 功能，请先启动对应的 MCP 服务器并配置 `mcp.json`

## 文件详细说明

### 应用层 (backend/app/)

#### `backend/app/main.py`
FastAPI 主应用入口文件，负责：
- 创建 FastAPI 应用实例
- 配置 CORS 中间件
- 注册 API 路由
- 定义应用生命周期（启动时加载 MCP 工具和 Skills）

#### `backend/app/api/__init__.py`
API 路由聚合器，将所有 API 路由模块整合为一个 `api_router`。

#### `backend/app/api/chat.py`
聊天接口模块，提供：
- `POST /api/chat` - 处理用户对话请求，调用 LLM 服务并返回响应

#### `backend/app/api/skills.py`
Skills 管理 API，提供：
- `GET /api/skills` - 获取所有已加载的技能列表
- `POST /api/skills/upload` - 上传新的 Skill（支持 .zip 格式）
- `DELETE /api/skills/{skill_name}` - 删除指定技能

#### `backend/app/api/tools.py`
MCP 工具 API，提供：
- `GET /api/tools` - 获取所有可用的 MCP 工具列表（支持 `?reload=true` 重新加载）
- `POST /api/call-tool` - 调用指定的 MCP 工具

### 核心层 (backend/core/)

#### `backend/core/config.py`
配置管理模块，使用 Pydantic Settings 管理环境变量：
- `OPENAI_API_KEY` - OpenAI API 密钥
- `OPENAI_API_BASE` - API 基础 URL
- `LLM_MODEL` - 使用的模型名称
- `TEMPERATURE` - 生成温度
- `MAX_RETRIES` - 最大重试次数
- `MCP_CONFIG_PATH` - MCP 配置文件路径
- `SKILLS_DIRECTORY` - Skills 主存储目录
- `SKILLS_EXTRA_DIRS` - 额外 Skills 目录（逗号分隔）
- `SKILLS_MAX_IN_PROMPT` - 最大 skill 数量，超过用紧凑格式
- `SKILLS_MAX_PROMPT_CHARS` - 最大字符数，超过用紧凑格式

#### `backend/core/exceptions.py`
自定义异常类定义：
- `AgentException` - Agent 基础异常
- `LLMException` - LLM 相关异常
- `MCPException` - MCP 相关异常
- `SkillException` - Skill 相关异常
- 以及各类具体异常（如 `MCPConnectionError`、`SkillNotFoundError` 等）

### LLM 模块 (backend/llm/)

#### `backend/llm/openai_service.py`
OpenAI 服务实现，包含：

**MessageBuilder 类**
- 构建发送给 LLM 的消息结构
- 整合系统提示词和 Skills 信息

**ToolExecutor 类**
- 执行 MCP 工具调用
- 解析工具返回结果

**OpenAIService 类**
- 初始化 OpenAI 异步客户端
- 构建 OpenAI 工具定义格式
- 处理对话请求和工具调用循环

### MCP 客户端模块 (backend/mcp_client/)

#### `backend/mcp_client/client.py`
MCP 客户端实现：

**MCPClient 类**
- 加载 MCP 服务器配置
- 连接 MCP 服务器并获取工具列表
- 调用 MCP 工具并返回结果

**全局实例 `mcp_client`**
- 项目启动时自动初始化的单例实例

### Skills 模块 (backend/skills/)

#### `backend/skills/manager.py`
Skill 管理器：

**SkillManager 类**
- 管理技能的加载、获取、删除
- 支持多来源加载（多个目录）
- 构建 Skills 系统提示词（支持紧凑格式）
- 热重载支持（文件变化自动刷新）
- Token 优化（自动切换紧凑格式）
- 维护技能注册表

**全局实例 `skill_manager`**
- 项目启动时自动初始化的单例实例

#### `backend/skills/watcher.py`
Skill 文件监视器：

**SkillWatcher 类**
- 使用 watchdog 监控 skill 文件变化
- 支持 SKILL.md 和 .zip 文件变化检测
- 防抖机制（500ms）
- 自动重新加载 skills

**SkillFileHandler 类**
- 处理文件创建、修改、删除事件
- 触发 reload 回调

#### `backend/skills/loader.py`
Skill 加载器：

**SkillLoader 类**
- 从多个目录加载 Skill（多来源）
- 从 ZIP 压缩包加载 Skill
- 扫描 SKILL.md 文件
- 批量加载目录下所有 Skill

**`sanitize_filename()` 函数**
- 处理 Windows 不兼容的文件名字符

#### `backend/skills/parser.py`
SKILL.md 解析器：

**SkillParser 类**
- 解析 SKILL.md 文件的 YAML frontmatter
- 提取技能名称、描述、元数据等信息
- 验证必需字段

### 数据模型层 (backend/models/)

#### `backend/models/chat.py`
聊天相关数据模型：
- `ChatRequest` - 对话请求模型
- `ChatResponse` - 对话响应模型
- `ChatMessage` - 消息模型
- `CallToolResult` - 工具调用结果模型

#### `backend/models/common.py`
通用数据模型：
- `CallToolRequest` - 工具调用请求模型

#### `backend/models/mcp.py`
MCP 相关数据模型：
- `MCPServerConfig` - MCP 服务器配置模型
- `MCPToolInfo` - MCP 工具信息模型

#### `backend/models/skill.py`
Skill 相关数据模型：
- `SkillInfo` - 技能信息模型
- `SkillMetadata` - 技能元数据模型

### 配置文件

#### `backend/mcp.json`
MCP 服务器配置文件，定义可连接的 MCP 服务器：
```json
{
  "mcpServers": {
    "server-name": {
      "url": "http://localhost:3000/mcp",
      "description": "服务器描述"
    }
  }
}
```

#### `backend/pyproject.toml`
项目配置文件，包含：
- 项目名称、版本、描述
- Python 版本要求
- 依赖列表
- 构建系统配置

#### `backend/.env.example`
环境变量示例模板，用于指导用户配置 `.env` 文件。

```env
# LLM 配置
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
TEMPERATURE=0.7
MAX_RETRIES=3

# MCP 配置
MCP_CONFIG_PATH=mcp.json

# Skills 配置
SKILLS_DIRECTORY=storage/skills
SKILLS_EXTRA_DIRS=                    # 额外技能目录，逗号分隔
SKILLS_MAX_IN_PROMPT=50             # 最大 skill 数量
SKILLS_MAX_PROMPT_CHARS=8000        # 最大字符数
```

### 前端 (frontend/)

#### `frontend/src/App.tsx`
主应用组件，包含侧边栏和内容区域切换。

#### `frontend/src/components/Chat.tsx`
聊天面板组件，提供：
- 消息发送/接收
- 工具调用结果展示
- 加载状态

#### `frontend/src/components/Sidebar.tsx`
侧边栏组件，包含：
- `Sidebar` - 导航侧边栏
- `ToolsPanel` - MCP 工具管理面板
- `SkillsPanel` - 技能管理面板

#### `frontend/src/api/index.ts`
API 调用层，封装所有后端 API 调用。

#### `frontend/src/types/index.ts`
TypeScript 类型定义。

## 数据流

1. **用户请求** → `frontend` 发送请求
2. **API 代理** → Vite 开发服务器代理到后端
3. **后端处理** → `backend/app/api/chat.py` 接收
4. **构建消息** → `backend/llm/openai_service.py` 的 `MessageBuilder`
5. **调用 LLM** → `OpenAIService.chat()`
6. **工具调用**（如需要）→ `ToolExecutor.execute_tool_call()`
7. **MCP 调用** → `backend/mcp_client/client.py`
8. **返回结果** → `ChatResponse` → 前端显示

## Skills 系统高级特性

### 多来源加载

Skills 支持从多个目录加载，通过 `SKILLS_EXTRA_DIRS` 配置：

```env
SKILLS_DIRECTORY=storage/skills
SKILLS_EXTRA_DIRS=~/.claude/skills,C:\Users\custom\skills
```

相同名称的 skill 只会加载一次，优先使用先配置的目录中的版本。

### 热重载

当 `storage/skills/` 目录下的 `SKILL.md` 或 `.zip` 文件发生变化时，系统会自动重新加载 skills。无需重启服务。

### Token 优化

当 skill 数量或字符数超过阈值时，自动切换到紧凑格式：

- **Verbose 格式**：包含 name + description
- **Compact 格式**：只包含 name + location（文件路径）

可配置项：
- `SKILLS_MAX_IN_PROMPT=50` - 最大 skill 数量
- `SKILLS_MAX_PROMPT_CHARS=8000` - 最大字符数

## 扩展指南

### 添加新的 MCP 服务器
在 `backend/mcp.json` 中添加服务器配置，点击刷新按钮即可加载。

### 添加新的 Skill
1. 创建 Skill 目录，包含 `SKILL.md` 文件
2. 打包为 ZIP 或直接放入 `backend/storage/skills/` 目录
3. 应用启动时自动加载，或通过前端界面上传

### 添加新的 LLM 服务
1. 在 `backend/llm/` 目录创建新的服务文件
2. 实现 `OpenAIService` 类似接口
3. 在配置中添加 LLM 选择选项

### 前端自定义
- 修改 `frontend/src/index.css` 中的 CSS 变量可自定义主题颜色
- 暗色主题为默认主题，使用 HSL 颜色空间
