# Agent Demo

<div align="center">

一个可扩展的 AI Agent Demo 框架，支持 MCP、Skills 及更多功能

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.1+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 📖 项目简介

Agent Demo 是一个基于 FastAPI 构建的现代化 AI Agent 框架，支持 MCP 协议、Skills 系统以及更多扩展功能。它提供了一个灵活、可扩展的架构，是一个可以用来整活和学习的智能应用。

## ✨ 核心特性

- 🔌 **MCP 协议支持**: 完整支持 Model Context Protocol，可以连接各种 MCP 服务器
- 🎯 **Skills 系统**: 灵活的技能管理，支持从压缩包加载和动态管理
- 🤖 **多模型支持**: 支持 OpenAI 兼容的 LLM 服务(OpenAI、DeepSeek、Claude 等)
- 🚀 **RESTful API**: 提供完整的 HTTP API 接口
- 📦 **模块化架构**: 清晰的分层设计，易于维护和扩展
- ⚡ **异步处理**: 基于 asyncio 的高性能异步架构
- 🔧 **工具调用**: 支持自动工具调用和多轮对话
- 💾 **会话管理**: 支持多会话管理和历史记录
- 🔮 **更多功能**: 持续扩展中...

## 🛠️ 技术栈

### 核心框架
- **FastAPI** - 现代高性能 Web 框架
- **Pydantic** - 数据验证和设置管理
- **Pydantic Settings** - 环境变量和配置管理

### AI & LLM
- **OpenAI SDK** - OpenAI API 客户端
- **MCP SDK** - Model Context Protocol SDK

### 工具库
- **httpx** - 异步 HTTP 客户端
- **PyYAML** - YAML 解析器
- **python-dotenv** - 环境变量管理

## 📁 项目结构

```
agent-demo/
├── app/                           # 应用层
│   ├── main.py                    # FastAPI 主应用
│   └── api/                       # API 路由
│       ├── chat.py               # 聊天接口
│       ├── skills.py             # Skills 管理
│       └── tools.py              # MCP 工具管理
│
├── core/                          # 核心层
│   ├── config.py                  # 配置管理
│   └── exceptions.py              # 自定义异常
│
├── llm/                           # LLM 模块
│   └── openai_service.py          # OpenAI 服务实现
│
├── mcp_client/                    # MCP 客户端模块
│   └── client.py                  # MCP 客户端实现
│
├── skills/                        # Skills 模块
│   ├── manager.py                 # Skill 管理器
│   ├── loader.py                  # Skill 加载器
│   └── parser.py                  # SKILL.md 解析器
│
├── models/                        # 数据模型层
│   ├── chat.py                    # 聊天模型
│   ├── mcp.py                     # MCP 模型
│   ├── skill.py                   # Skill 模型
│   └── common.py                  # 通用模型
│
├── storage/                       # 存储层
│   └── skills/                    # Skills 文件存储
│
├── public/                        # 前端静态文件
│   └── index.html
│
├── .env                           # 环境变量
├── .env.example                   # 环境变量示例
├── mcp.json                       # MCP 服务器配置
└── pyproject.toml                 # 项目配置
```

## 🚀 快速开始

### 环境要求

- Python 3.12 或更高版本
- uv 包管理器(推荐)或 pip

### 安装步骤

1. **克隆项目**
```bash
git clone <repository-url>
cd agent-demo
```

2. **安装依赖**
```bash
# 使用 uv(推荐)
uv sync

# 或使用 pip
pip install -r requirements.txt
```

3. **配置环境变量**
```bash
# 复制环境变量模板
cp .env.example .env

# 编辑 .env 文件,填入你的配置
```

4. **配置 MCP 服务器**
```json
// mcp.json
{
  "mcpServers": {
    "your-server-name": {
      "url": "http://localhost:3000/mcp"
    }
  }
}
```

5. **启动应用**
```bash
# 使用 uv
uv run python -m app.main

# 或直接运行
python -m app.main
```

应用将在 `http://localhost:8002` 启动

## 📝 配置说明

### 环境变量配置

在 `.env` 文件中配置以下变量:

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
```

### MCP 服务器配置

在 `mcp.json` 中配置 MCP 服务器:

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

### 1. MCP 工具调用

Agent Demo 支持自动发现和调用 MCP 服务器提供的工具:

```python
# 获取所有可用工具
GET /api/tools

# 调用工具
POST /api/call-tool
{
  "server": "server-name",
  "name": "tool-name",
  "args": {
    "arg1": "value1"
  }
}
```

### 2. Skills 系统

Skills 系统允许你为 AI Agent 添加特定领域的技能:

**Skill 文件结构:**
```
skill-name/
├── SKILL.md              # 必需 - 主 Skill 文件
├── scripts/              # 可选 - 可执行脚本
├── references/           # 可选 - 参考文档
└── assets/               # 可选 - 资源文件
```

**SKILL.md 格式:**
```markdown
---
name: skill-name
description: 技能描述。当用户提到 [特定短语] 时使用。
license: MIT
compatibility: 兼容性说明
metadata:
  author: 作者名
  version: "1.0.0"
---

# 技能标题

## 使用时机
说明何时应该使用此技能

## 功能说明
详细的功能描述

## 示例
具体的使用示例
```

**Skills API:**
```http
# 获取所有 Skills
GET /api/skills

# 上传 Skill
POST /api/skills/upload
Content-Type: multipart/form-data

# 删除 Skill
DELETE /api/skills/{skill_name}
```

### 3. 对话功能

支持多轮对话和自动工具调用:

```http
POST /api/chat
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "帮我分析这段代码",
  "history": []
}
```

## 📚 API 文档

### 聊天接口

**POST /api/chat**

发起对话请求

请求体:
```json
{
  "session_id": "string",
  "message": "string",
  "history": [
    {
      "role": "user",
      "content": "string"
    }
  ]
}
```

响应:
```json
{
  "response": "AI 的回复",
  "tool_calls": [],
  "history": []
}
```

### Skills 管理

**GET /api/skills**

获取所有已加载的 Skills

**POST /api/skills/upload**

上传新的 Skill(支持 .zip 格式)

**DELETE /api/skills/{skill_name}**

删除指定的 Skill

### MCP 工具

**GET /api/tools**

获取所有可用的 MCP 工具

**POST /api/call-tool**

调用指定的 MCP 工具

## 🔧 开发指南

### 添加新的 LLM 服务

1. 在 `llm/` 目录创建新的服务文件
2. 继承基础接口并实现方法
3. 在配置中添加新的 LLM 选项

### 添加新的 Skill

1. 创建 Skill 目录和 SKILL.md 文件
2. 打包为 .zip 文件
3. 通过 API 上传或直接放在 `storage/skills/` 目录

### 添加新的 MCP 服务器

1. 在 `mcp.json` 中添加服务器配置
2. 重启应用自动加载

## 🎨 架构设计

### 分层架构

- **应用层 (app/)**: 处理 HTTP 请求和响应
- **核心层 (core/)**: 配置管理和核心逻辑
- **LLM 层 (llm/)**: 大语言模型交互
- **MCP 层 (mcp_client/)**: MCP 协议实现
- **Skills 层 (skills/)**: 技能管理
- **模型层 (models/)**: 数据模型定义
- **存储层 (storage/)**: 数据持久化

### 设计模式

- **依赖注入**: 组件解耦,便于测试
- **单一职责**: 每个模块专注单一功能
- **开闭原则**: 对扩展开放,对修改关闭
- **接口隔离**: 使用小而专一的接口

## 📖 最佳实践

1. **Skills 设计**
   - 保持单一职责
   - 提供清晰的描述
   - 包含使用示例

2. **错误处理**
   - 使用自定义异常
   - 提供有意义的错误信息
   - 记录详细的日志

3. **性能优化**
   - 使用异步操作
   - 合理使用缓存
   - 避免阻塞操作

## 🐛 故障排除

#### Skill 未加载
- 检查 SKILL.md 文件是否存在
- 验证 YAML frontmatter 格式
- 确保 name 和 description 字段存在

#### MCP 连接失败
- 检查 MCP 服务器是否运行
- 验证 mcp.json 配置
- 检查网络连接

#### LLM 调用失败
- 验证 API Key 是否正确
- 检查 API Base URL
- 确认模型名称正确

## 🤝 贡献指南

欢迎贡献代码一起整活做好玩的东西，报告问题或提出建议!

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/AmazingFeature`)
3. 提交更改 (`git commit -m 'Add some AmazingFeature'`)
4. 推送到分支 (`git push origin feature/AmazingFeature`)
5. 开启 Pull Request

## 📄 许可证

本项目采用 MIT 许可证 - 查看 [LICENSE](LICENSE) 文件了解详情

## 🙏 致谢

- [FastAPI](https://fastapi.tiangolo.com/) - 现代高性能 Web 框架
- [OpenAI](https://openai.com/) - AI 研究和部署
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- [Pydantic](https://pydantic-docs.helpmanual.io/) - 数据验证
