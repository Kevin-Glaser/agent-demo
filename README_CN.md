# Agent Demo

<div align="center">

一个可扩展的 AI Agent Demo 框架，支持 MCP、Skills 及更多功能

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.1+-green.svg)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 📖 项目简介

Agent Demo 是一个现代化的 AI Agent 框架，采用前后端分离架构。后端基于 FastAPI 构建，支持 MCP 协议和 Skills 系统；前端基于 React + Vite 构建，拥有简洁的暗色主题界面。

## ✨ 核心特性

- 🔌 **MCP 协议支持**: 完整支持 Model Context Protocol，可以连接各种 MCP 服务器
- 🎯 **Skills 系统**: 灵活的技能管理，支持从压缩包加载和动态管理
- 🤖 **多模型支持**: 支持 OpenAI 兼容的 LLM 服务(OpenAI、DeepSeek、Claude 等)
- 🚀 **RESTful API**: 提供完整的 HTTP API 接口
- 📦 **模块化架构**: 清晰的分层设计，易于维护和扩展
- ⚡ **异步处理**: 基于 asyncio 的高性能异步架构
- 🎨 **暗色主题 UI**: 现代 React 前端界面
- 🔧 **工具调用**: 支持自动工具调用和多轮对话

> 📁 详细的项目结构和文件说明请参考 [AGENTS.md](AGENTS.md)

## 🛠️ 技术栈

### 后端
- **FastAPI** - 现代高性能 Web 框架
- **Pydantic** - 数据验证和设置管理
- **OpenAI SDK** - OpenAI API 客户端
- **MCP SDK** - Model Context Protocol SDK

### 前端
- **React 18** - UI 库
- **Vite** - 构建工具和开发服务器
- **TypeScript** - 类型安全
- **Tailwind CSS** - 工具类 CSS
- **Lucide React** - 图标库

## 🚀 快速开始

### 环境要求

- Python 3.12 或更高版本
- Node.js 18 或更高版本
- pnpm 包管理器
- uv 包管理器

### 安装步骤

#### 1. 后端

```bash
cd backend

# 创建虚拟环境
uv venv

# 安装依赖
uv sync

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，填入必要的配置
```

#### 2. 前端

```bash
cd frontend

# 安装依赖
pnpm install
```

### 启动服务

#### 启动后端（在 backend 目录）

```bash
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002
```

#### 启动前端（在 frontend 目录）

```bash
pnpm dev
```

前端将在 `http://localhost:5173` 启动，并自动代理 API 请求到后端 `http://localhost:8002`。

## 📝 配置说明

### 后端环境变量

在 `backend/.env` 文件中配置以下变量：

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

### MCP 服务器配置

在 `backend/mcp.json` 中配置 MCP 服务器：

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

## 🎯 功能详解

### 1. 聊天界面

现代暗色主题聊天界面，支持：
- 多轮对话
- 工具调用结果展示
- 加载状态

### 2. MCP 工具管理

- 查看所有可用的 MCP 工具
- 点击刷新按钮重新加载工具
- 直接在界面调用工具

### 3. Skills 系统

- 上传 .zip 格式的技能包
- 查看已安装的技能
- 删除技能
- 热重载：文件变化时自动重新加载
- Token 优化：超过限制时自动切换紧凑格式

## 📁 项目结构

```
agent-demo/
├── frontend/              # React + Vite 前端
│   ├── src/
│   │   ├── api/          # API 调用
│   │   ├── components/    # React 组件
│   │   ├── types/        # TypeScript 类型
│   │   └── App.tsx       # 主应用
│   └── package.json
│
├── backend/               # FastAPI 后端
│   ├── app/             # 应用层
│   ├── core/            # 核心工具
│   ├── llm/             # LLM 集成
│   ├── mcp_client/      # MCP 客户端
│   ├── models/          # 数据模型
│   ├── skills/          # 技能管理
│   └── storage/         # 文件存储
│
├── README.md
├── README_CN.md
└── AGENTS.md
```

## 🐛 故障排除

#### Skill 未加载
- 检查 zip 包中是否包含 SKILL.md 文件
- 验证 YAML frontmatter 格式
- 确保 name 和 description 字段存在
- 技能名称中的特殊字符（如 `:`）会为 Windows 兼容性进行转换

#### MCP 连接失败
- 检查 MCP 服务器是否运行
- 验证 mcp.json 配置
- 点击刷新按钮重新加载工具

#### 前端 API 错误
- 确保后端在 8002 端口运行
- 检查后端 CORS 设置

## 🤝 贡献指南

欢迎贡献代码一起整活做好玩的东西，报告问题或提出建议！

## 📄 许可证

本项目采用 MIT 许可证。

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能 Web 框架
- [React](https://react.dev/) - UI 库
- [Vite](https://vitejs.dev/) - 构建工具
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
