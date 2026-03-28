# Agent Demo 项目文档

## 项目概述

Agent Demo 是一个基于 FastAPI 构建的现代化 AI Agent 框架，支持 MCP 协议、Skills 系统以及更多扩展功能。项目采用分层架构设计，模块化程度高，易于扩展和维护。

> 本文档详细说明项目结构和各文件作用，快速入门请参考 [README.md](README.md) 或 [README_CN.md](README_CN.md)

## 快速开始

### 环境要求

- Python 3.12+
- uv 包管理器

### 安装步骤

1. **创建虚拟环境**
   ```bash
   uv venv
   ```

2. **初始化项目**（如果是新克隆的项目）
   ```bash
   uv init
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

5. **启动后端服务**
   ```bash
   uv run python app/main.py
   ```
   
   或者使用 uvicorn：
   ```bash
   uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
   ```

### 注意事项

- 必须先进入虚拟环境才能执行 `uv run` 命令
- 确保 `.env` 文件中已正确配置 `OPENAI_API_KEY` 等必要参数
- 如需使用 MCP 功能，请先启动对应的 MCP 服务器并配置 `mcp.json`

## 项目结构

```
agent-demo/
├── app/                           # 应用层
│   ├── __init__.py               # 应用模块初始化
│   ├── main.py                   # FastAPI 主应用入口
│   └── api/                      # API 路由层
│       ├── __init__.py           # API 模块初始化，聚合所有路由
│       ├── chat.py               # 聊天接口 - 处理对话请求
│       ├── skills.py             # Skills 管理 API - 上传/删除/获取技能
│       └── tools.py              # MCP 工具 API - 获取/调用工具
│
├── core/                          # 核心层
│   ├── __init__.py               # 核心模块初始化
│   ├── config.py                 # 配置管理 - 环境变量和设置
│   └── exceptions.py             # 自定义异常类
│
├── llm/                           # LLM 模块
│   ├── __init__.py               # LLM 模块初始化
│   └── openai_service.py         # OpenAI 服务 - LLM 调用和工具执行
│
├── mcp_client/                    # MCP 客户端模块
│   ├── __init__.py               # MCP 模块初始化
│   └── client.py                 # MCP 客户端 - 连接和调用 MCP 服务器
│
├── skills/                        # Skills 模块
│   ├── __init__.py               # Skills 模块初始化
│   ├── manager.py                # Skill 管理器 - 管理技能生命周期
│   ├── loader.py                 # Skill 加载器 - 从目录/压缩包加载
│   └── parser.py                 # SKILL.md 解析器 - 解析技能定义文件
│
├── models/                        # 数据模型层
│   ├── __init__.py               # 模型模块初始化
│   ├── chat.py                   # 聊天相关模型 - 请求/响应结构
│   ├── common.py                 # 通用模型 - 工具调用请求等
│   ├── mcp.py                    # MCP 相关模型 - 服务器配置/工具信息
│   └── skill.py                  # Skill 相关模型 - 技能信息/元数据
│
├── storage/                       # 存储层
│   └── skills/                   # Skills 文件存储目录
│
├── public/                        # 前端静态文件
│   └── index.html                # Web 界面入口
│
├── .env                          # 环境变量配置（不提交到 Git）
├── .env.example                  # 环境变量示例模板
├── .gitignore                    # Git 忽略规则
├── .python-version               # Python 版本指定
├── mcp.json                      # MCP 服务器配置
├── pyproject.toml                # 项目配置和依赖
├── uv.lock                       # 依赖锁定文件
├── README.md                     # 英文文档
├── README_CN.md                  # 中文文档
└── AGENTS.md                     # 本文档
```

## 文件详细说明

### 应用层 (app/)

#### `app/main.py`
FastAPI 主应用入口文件，负责：
- 创建 FastAPI 应用实例
- 配置 CORS 中间件
- 注册 API 路由
- 挂载静态文件服务
- 定义应用生命周期（启动时加载 MCP 工具和 Skills）

#### `app/api/__init__.py`
API 路由聚合器，将所有 API 路由模块整合为一个 `api_router`。

#### `app/api/chat.py`
聊天接口模块，提供：
- `POST /api/chat` - 处理用户对话请求，调用 LLM 服务并返回响应

#### `app/api/skills.py`
Skills 管理 API，提供：
- `GET /api/skills` - 获取所有已加载的技能列表
- `POST /api/skills/upload` - 上传新的 Skill（支持 .zip 格式）
- `DELETE /api/skills/{skill_name}` - 删除指定技能

#### `app/api/tools.py`
MCP 工具 API，提供：
- `GET /api/tools` - 获取所有可用的 MCP 工具列表
- `POST /api/call-tool` - 调用指定的 MCP 工具

### 核心层 (core/)

#### `core/config.py`
配置管理模块，使用 Pydantic Settings 管理环境变量：
- `OPENAI_API_KEY` - OpenAI API 密钥
- `OPENAI_API_BASE` - API 基础 URL
- `LLM_MODEL` - 使用的模型名称
- `TEMPERATURE` - 生成温度
- `MAX_RETRIES` - 最大重试次数
- `MCP_CONFIG_PATH` - MCP 配置文件路径
- `SKILLS_DIRECTORY` - Skills 存储目录

#### `core/exceptions.py`
自定义异常类定义：
- `AgentException` - Agent 基础异常
- `LLMException` - LLM 相关异常
- `MCPException` - MCP 相关异常
- `SkillException` - Skill 相关异常
- 以及各类具体异常（如 `MCPConnectionError`、`SkillNotFoundError` 等）

### LLM 模块 (llm/)

#### `llm/openai_service.py`
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

### MCP 客户端模块 (mcp_client/)

#### `mcp_client/client.py`
MCP 客户端实现：

**MCPClient 类**
- 加载 MCP 服务器配置
- 连接 MCP 服务器并获取工具列表
- 调用 MCP 工具并返回结果

**全局实例 `mcp_client`**
- 项目启动时自动初始化的单例实例

### Skills 模块 (skills/)

#### `skills/manager.py`
Skill 管理器：

**SkillManager 类**
- 管理技能的加载、获取、删除
- 构建 Skills 系统提示词
- 维护技能注册表

**全局实例 `skill_manager`**
- 项目启动时自动初始化的单例实例

#### `skills/loader.py`
Skill 加载器：

**SkillLoader 类**
- 从目录加载 Skill
- 从 ZIP 压缩包加载 Skill
- 批量加载目录下所有 Skill

#### `skills/parser.py`
SKILL.md 解析器：

**SkillParser 类**
- 解析 SKILL.md 文件的 YAML frontmatter
- 提取技能名称、描述、元数据等信息
- 验证必需字段

### 数据模型层 (models/)

#### `models/chat.py`
聊天相关数据模型：
- `ChatRequest` - 对话请求模型
- `ChatResponse` - 对话响应模型
- `ChatMessage` - 消息模型
- `CallToolResult` - 工具调用结果模型

#### `models/common.py`
通用数据模型：
- `CallToolRequest` - 工具调用请求模型

#### `models/mcp.py`
MCP 相关数据模型：
- `MCPServerConfig` - MCP 服务器配置模型
- `MCPToolInfo` - MCP 工具信息模型

#### `models/skill.py`
Skill 相关数据模型：
- `SkillInfo` - 技能信息模型
- `SkillMetadata` - 技能元数据模型

### 配置文件

#### `mcp.json`
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

#### `pyproject.toml`
项目配置文件，包含：
- 项目名称、版本、描述
- Python 版本要求
- 依赖列表
- 构建系统配置

#### `.env.example`
环境变量示例模板，用于指导用户配置 `.env` 文件。

### 前端文件

#### `public/index.html`
Web 界面入口文件，提供用户交互界面。

## 数据流

1. **用户请求** → `app/api/chat.py` 接收
2. **构建消息** → `llm/openai_service.py` 的 `MessageBuilder`
3. **调用 LLM** → `OpenAIService.chat()`
4. **工具调用**（如需要）→ `ToolExecutor.execute_tool_call()`
5. **MCP 调用** → `mcp_client/client.py`
6. **返回结果** → `ChatResponse`

## 扩展指南

### 添加新的 MCP 服务器
在 `mcp.json` 中添加服务器配置，重启应用即可自动加载。

### 添加新的 Skill
1. 创建 Skill 目录，包含 `SKILL.md` 文件
2. 打包为 ZIP 或直接放入 `storage/skills/` 目录
3. 应用启动时自动加载，或通过 API 上传

### 添加新的 LLM 服务
1. 在 `llm/` 目录创建新的服务文件
2. 实现 `OpenAIService` 类似接口
3. 在配置中添加 LLM 选择选项
