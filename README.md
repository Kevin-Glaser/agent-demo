# Agent Demo

<div align="center">

An extensible AI Agent Demo framework with MCP, Skills, and more

[![Python Version](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135.1+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

</div>

---

## 📖 Overview

Agent Demo is a modern AI Agent framework built on FastAPI, supporting MCP protocol, Skills system, and more extensible features. It provides a flexible, extensible architecture that is perfect for building fun projects and learning about intelligent applications.

## ✨ Key Features

- 🔌 **MCP Protocol Support**: Full support for Model Context Protocol, connecting to various MCP servers
- 🎯 **Skills System**: Flexible skill management with zip package loading and dynamic management
- 🤖 **Multi-Model Support**: Support for OpenAI-compatible LLM services (OpenAI, DeepSeek, Claude, etc.)
- 🚀 **RESTful API**: Complete HTTP API interface
- 📦 **Modular Architecture**: Clear layered design for easy maintenance and extension
- ⚡ **Async Processing**: High-performance async architecture based on asyncio
- 🔧 **Tool Calling**: Support for automatic tool calling and multi-turn conversations
- 💾 **Session Management**: Support for multi-session management and history
- 🔮 **More Features**: Continuously expanding...

## 🛠️ Tech Stack

### Core Framework
- **FastAPI** - Modern high-performance web framework
- **Pydantic** - Data validation and settings management
- **Pydantic Settings** - Environment variable and configuration management

### AI & LLM
- **OpenAI SDK** - OpenAI API client
- **MCP SDK** - Model Context Protocol SDK

### Utilities
- **httpx** - Async HTTP client
- **PyYAML** - YAML parser
- **python-dotenv** - Environment variable management

## 📁 Project Structure

```
agent-demo/
├── app/                           # Application Layer
│   ├── main.py                    # FastAPI main application
│   └── api/                       # API routes
│       ├── chat.py               # Chat endpoints
│       ├── skills.py             # Skills management
│       └── tools.py              # MCP tools management
│
├── core/                          # Core Layer
│   ├── config.py                  # Configuration management
│   └── exceptions.py              # Custom exceptions
│
├── llm/                           # LLM Module
│   └── openai_service.py          # OpenAI service implementation
│
├── mcp_client/                    # MCP Client Module
│   └── client.py                  # MCP client implementation
│
├── skills/                        # Skills Module
│   ├── manager.py                 # Skill manager
│   ├── loader.py                  # Skill loader
│   └── parser.py                  # SKILL.md parser
│
├── models/                        # Data Models Layer
│   ├── chat.py                    # Chat models
│   ├── mcp.py                     # MCP models
│   ├── skill.py                   # Skill models
│   └── common.py                  # Common models
│
├── storage/                       # Storage Layer
│   └── skills/                    # Skills file storage
│
├── public/                        # Frontend static files
│   └── index.html
│
├── .env                           # Environment variables
├── .env.example                   # Environment variables example
├── mcp.json                       # MCP server configuration
└── pyproject.toml                 # Project configuration
```

## 🚀 Quick Start

### Requirements

- Python 3.12 or higher
- uv package manager (recommended) or pip

### Installation

1. **Clone the repository**
```bash
git clone <repository-url>
cd agent-demo
```

2. **Install dependencies**
```bash
# Using uv (recommended)
uv sync

# Or using pip
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
# Copy environment template
cp .env.example .env

# Edit .env file with your configuration
```

4. **Configure MCP servers**
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

5. **Run the application**
```bash
# Using uv
uv run python -m app.main

# Or run directly
python -m app.main
```

The application will start at `http://localhost:8002`

## 📝 Configuration

### Environment Variables

Configure the following variables in `.env` file:

```env
# LLM Configuration
OPENAI_API_KEY=your_api_key_here
OPENAI_API_BASE=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
TEMPERATURE=0.7
MAX_RETRIES=3

# MCP Configuration
MCP_CONFIG_PATH=mcp.json

# Skills Configuration
SKILLS_DIRECTORY=storage/skills
```

### MCP Server Configuration

Configure MCP servers in `mcp.json`:

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

## 🎯 Features

### 1. MCP Tool Calling

Agent Demo supports automatic discovery and calling of tools provided by MCP servers:

```python
# Get all available tools
GET /api/tools

# Call a tool
POST /api/call-tool
{
  "server": "server-name",
  "name": "tool-name",
  "args": {
    "arg1": "value1"
  }
}
```

### 2. Skills System

The Skills system allows you to add domain-specific skills to your AI Agent:

**Skill File Structure:**
```
skill-name/
├── SKILL.md              # Required - Main Skill file
├── scripts/              # Optional - Executable scripts
├── references/           # Optional - Reference documents
└── assets/               # Optional - Resource files
```

**SKILL.md Format:**
```markdown
---
name: skill-name
description: Skill description. Use when user mentions [specific phrases].
license: MIT
compatibility: Compatibility notes
metadata:
  author: Author name
  version: "1.0.0"
---

# Skill Title

## When to Use
Explain when this skill should be used

## Functionality
Detailed functionality description

## Examples
Specific usage examples
```

**Skills API:**
```http
# Get all Skills
GET /api/skills

# Upload Skill
POST /api/skills/upload
Content-Type: multipart/form-data

# Delete Skill
DELETE /api/skills/{skill_name}
```

### 3. Chat Functionality

Support for multi-turn conversations and automatic tool calling:

```http
POST /api/chat
Content-Type: application/json

{
  "session_id": "session-123",
  "message": "Help me analyze this code",
  "history": []
}
```

## 📚 API Documentation

### Chat Endpoints

**POST /api/chat**

Initiate a chat request

Request body:
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

Response:
```json
{
  "response": "AI response",
  "tool_calls": [],
  "history": []
}
```

### Skills Management

**GET /api/skills**

Get all loaded Skills

**POST /api/skills/upload**

Upload a new Skill (supports .zip format)

**DELETE /api/skills/{skill_name}**

Delete a specific Skill

### MCP Tools

**GET /api/tools**

Get all available MCP tools

**POST /api/call-tool**

Call a specific MCP tool

## 🔧 Development Guide

### Adding a New LLM Service

1. Create a new service file in `llm/` directory
2. Inherit from base interface and implement methods
3. Add new LLM option in configuration

### Adding a New Skill

1. Create Skill directory and SKILL.md file
2. Package as .zip file
3. Upload via API or place directly in `storage/skills/` directory

### Adding a New MCP Server

1. Add server configuration in `mcp.json`
2. Restart application to auto-load

## 🎨 Architecture Design

### Layered Architecture

- **Application Layer (app/)**: Handle HTTP requests and responses
- **Core Layer (core/)**: Configuration management and core logic
- **LLM Layer (llm/)**: Large language model interaction
- **MCP Layer (mcp_client/)**: MCP protocol implementation
- **Skills Layer (skills/)**: Skill management
- **Models Layer (models/)**: Data model definitions
- **Storage Layer (storage/)**: Data persistence

### Design Patterns

- **Dependency Injection**: Component decoupling for easy testing
- **Single Responsibility**: Each module focuses on a single function
- **Open-Closed Principle**: Open for extension, closed for modification
- **Interface Segregation**: Use small and specialized interfaces

## 📖 Best Practices

1. **Skills Design**
   - Maintain single responsibility
   - Provide clear descriptions
   - Include usage examples

2. **Error Handling**
   - Use custom exceptions
   - Provide meaningful error messages
   - Log detailed information

3. **Performance Optimization**
   - Use async operations
   - Use caching appropriately
   - Avoid blocking operations

## 🐛 Troubleshooting

#### Skill Not Loading
- Check if SKILL.md file exists
- Verify YAML frontmatter format
- Ensure name and description fields exist

#### MCP Connection Failed
- Check if MCP server is running
- Verify mcp.json configuration
- Check network connection

#### LLM Call Failed
- Verify API Key is correct
- Check API Base URL
- Confirm model name is correct

## 🤝 Contributing

Contributions are welcome! Feel free to contribute code, report issues, or suggest ideas for fun projects!

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [FastAPI](https://fastapi.tiangolo.com/) - Modern high-performance web framework
- [OpenAI](https://openai.com/) - AI research and deployment
- [MCP](https://modelcontextprotocol.io/) - Model Context Protocol
- [Pydantic](https://pydantic-docs.helpmanual.io/) - Data validation
