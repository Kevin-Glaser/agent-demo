# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Agent Demo is an extensible AI Agent framework with MCP (Model Context Protocol) support, a Skills system, and multi-model LLM support. It consists of a FastAPI Python backend and a React + Vite + TypeScript frontend with Tailwind CSS.

## Environment Requirements

- Python 3.12+
- Node.js 18+
- pnpm package manager
- uv package manager

## Common Commands

### Backend

```bash
cd backend

# Create virtual environment
uv venv

# Install dependencies
uv sync

# Configure environment
cp .env.example .env   # Then edit .env with your API keys

# Run development server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8002

# Or run directly
uv run python -m app.main
```

### Frontend

```bash
cd frontend

# Install dependencies
pnpm install

# Development server (proxies /api to backend:8002)
pnpm dev

# Production build
pnpm build

# Preview production build
pnpm preview

# Lint
pnpm lint
```

## Architecture

### Data Flow
1. User message → React frontend → Vite proxy → `POST /api/chat`
2. `chat.py` → `OpenAIService.chat()` with `MessageBuilder`
3. LLM may call tools → `ToolExecutor` → MCP client
4. Response returned through the chain

### Key Components

**API Layer** (`backend/app/api/`):
- `chat.py`: POST /api/chat, POST /api/chat/stream, POST /api/chat/loop
- `skills.py`: GET/POST/DELETE /api/skills/* - skill management
- `tools.py`: GET /api/tools, POST /api/call-tool - MCP tool access

**LLM Service** (`backend/llm/openai_service.py`):
- `OpenAIService`: Main LLM interface with message building and tool execution
- `MessageBuilder`: Constructs prompts with skills info and conversation history
- `ToolExecutor`: Executes MCP tool calls

**Skills System** (`backend/skills/`):
- `SkillManager`: Lifecycle management, hot reload via watchdog (500ms debounce)
- `SkillLoader`: Loads from ZIP files or directories
- `SkillParser`: Parses YAML frontmatter in SKILL.md files
- Supports token-optimized compact/verbose formats

**Session Management** (`backend/session/`):
- `compaction.py`: ConversationCompaction, ConversationManager, SessionProcessor
- `token.py`: Token counting utilities (estimate, TokenUsage, TokenBudget)
- `CONVERSATION_AUTO_COMPACT` setting for automatic compaction

**MCP Client** (`backend/mcp_client/client.py`):
- Singleton `mcp_client` instance
- Config loaded from `mcp.json`
- Connects to MCP servers via HTTP

### Model Limits
Configured in `backend/core/config.py` via `ModelLimits` class. Supports DeepSeek, GPT-4o, Claude, and Qwen models with context/input/output limits.

## Skills System

### Multi-source Loading
Skills can be loaded from multiple directories via `SKILLS_EXTRA_DIRS`:
```env
SKILLS_DIRECTORY=storage/skills
SKILLS_EXTRA_DIRS=~/.claude/skills,C:\Users\custom\skills
```
Same-named skills only load once, prioritizing earlier-configured directories.

### Hot Reload
When files in `storage/skills/` change (SKILL.md or .zip), skills auto-reload via watchdog with 500ms debounce.

### Token Optimization
When skill count or character count exceeds thresholds, auto-switches to compact format:
- **Verbose**: name + description
- **Compact**: name + location (file path)

Configurable via:
- `SKILLS_MAX_IN_PROMPT=50` - max skills before switching
- `SKILLS_MAX_PROMPT_CHARS=8000` - max characters before switching

## Configuration Files

- `backend/mcp.json`: MCP server endpoints
  ```json
  {
    "mcpServers": {
      "server-name": {
        "url": "http://localhost:3000/mcp",
        "description": "Server description"
      }
    }
  }
  ```
- `backend/.env`: API keys (NOT committed to git)
- `backend/.env.example`: Environment variable template

### Environment Variables (from .env.example)
```env
# LLM Config
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
TEMPERATURE=0.7
MAX_RETRIES=3

# MCP Config
MCP_CONFIG_PATH=mcp.json

# Skills Config
SKILLS_DIRECTORY=storage/skills
SKILLS_EXTRA_DIRS=
SKILLS_MAX_IN_PROMPT=50
SKILLS_MAX_PROMPT_CHARS=8000

# Conversation Config
CONVERSATION_MAX_TOKENS=128000
CONVERSATION_RESERVED_TOKENS=20000
CONVERSATION_PRUNE_PROTECT=40000
CONVERSATION_AUTO_COMPACT=true
```

## Adding New Skills

1. Create a directory with `SKILL.md` file
2. Package as ZIP or place directly in `backend/storage/skills/`
3. Auto-loaded on startup, or upload via frontend

## Adding New MCP Server

Add server config to `backend/mcp.json`, then reload via API:
```bash
curl -X POST "http://localhost:8002/api/tools?reload=true"
```

## Key Source Files

| File | Purpose |
|------|---------|
| `backend/app/api/chat.py` | Chat endpoints (chat, stream, loop) |
| `backend/llm/openai_service.py` | LLM service, streaming, tool execution |
| `backend/session/compaction.py` | ConversationCompaction, ConversationManager, SessionProcessor |
| `backend/session/token.py` | Token estimation, TokenUsage, TokenBudget |
| `backend/skills/manager.py` | SkillManager - lifecycle, hot reload |
| `backend/skills/loader.py` | SkillLoader - ZIP/dir loading |
| `backend/skills/parser.py` | SKILL.md YAML frontmatter parser |
| `backend/mcp_client/client.py` | MCP client singleton |
| `backend/core/config.py` | Settings, ModelLimits |
