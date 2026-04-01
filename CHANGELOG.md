# Changelog

All notable changes to this project will be documented in this file.

## Version Number Requirements

- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

## [1.2.0] - 2026-04-01

### Added

#### Streaming Response
- **SSE Streaming**: `/api/chat/stream` and `/api/chat/loop` endpoints with SSE support
- **SSE Chunk Types**: text-delta, reasoning-delta, tool-call, tool-result, done, error
- **Real-time Display**: Incremental text streaming with stop button and tool call display

## [1.1.0] - 2026-04-01

### Added

#### Long Context Management
- **Token Management**: TokenUsage, CumulativeTokenTracker, TokenBudget, ModelLimits
- **Message Partitioning**: 12 PartType enums (TEXT/TOOL/REASONING/COMPACTION/FILE/SNAPSHOT/STEP_START/STEP_FINISH/PATCH/AGENT/SUBTASK/RETRY)
- **Compaction Flow**: overflow detection → prune → LLM summary + stripMedia
- **Streaming**: text-delta, reasoning-delta incremental events
- **Message Loop**: run_loop() with continue/compact/stop control flow

#### New API Endpoints
- `POST /api/chat/stream`: Streaming chat
- `POST /api/chat/loop`: Full conversation loop

## [1.0.0] - 2026-04-01

### Added

#### Core Features
- **MCP Protocol Support**: MCP client for connecting to MCP servers
- **Skills System**: Multi-source loading, hot reload, token optimization
- **FastAPI Backend**: Modern API backend

#### Project Structure
- `backend/app/`: Application layer - API routes and main entry
- `backend/core/`: Core layer - config and exceptions
- `backend/llm/`: LLM module - OpenAI service
- `backend/mcp_client/`: MCP client module
- `backend/skills/`: Skills module - management, loading, parsing, watching
- `backend/models/`: Data models
- `frontend/`: React + Vite frontend

#### API Endpoints
- `POST /api/chat`: Chat interface
- `GET /api/tools`: List available MCP tools
- `POST /api/call-tool`: Call MCP tool
- `GET /api/skills`: List loaded skills
- `POST /api/skills/upload`: Upload new skill
- `DELETE /api/skills/{skill_name}`: Delete skill

