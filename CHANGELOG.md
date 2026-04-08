# Changelog

All notable changes to this project will be documented in this file.

## Version Number Requirements

- MAJOR: Breaking changes
- MINOR: New features (backward compatible)
- PATCH: Bug fixes

## [1.4.0] - 2026-04-08

### Added

#### Advanced Session Compaction
- **Multi-level Pruning**: 4-level progressive strategy (contextual messages → tool results → reasoning → user boundary)
- **LLM Summarization**: Structured summary with Goal/Instructions/Discoveries/Accomplished/Relevant files
- **truncate_middle**: Token budget preserving start and end of large outputs
- **Contextual Detection**: Detect contextual messages for pruning (<model_switch>, <permissions>, <system-reminder>)
- **insertReminders**: Multi-turn conversation reminder injection

#### Session History Operations
- **rollback**: Rollback message history by Turn number or index
- **delete_turn**: Delete specific Turn
- **remove_oldest_messages**: FIFO strategy to remove oldest messages

#### New API Endpoints
- `POST /api/chat/rollback`: Rollback message history
- `POST /api/chat/delete-turn`: Delete specific turn

#### Frontend Enhancements
- **Rollback/Delete UI**: Add rollback and delete buttons in the user interface

### Fixed
- **chat_stream SSE**: SSE chunk for plain text response

## [1.3.0] - 2026-04-07

### Added

#### Reasoning Model Detection
- **Config-driven Detection**: `REASONING_MODELS` setting for explicit model list
- **Fallback Pattern Matching**: `REASONING_MODEL_PATTERNS` setting (default: "r1,o1,o3")
- **Extensible Fields**: `_extract_reasoning()` now checks multiple provider fields (reasoning, completion_reasoning, thinking, thought_process, opaque.reasoning)
- **Nested Attribute Support**: `_get_nested_reasoning()` handles dot-notation paths

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

