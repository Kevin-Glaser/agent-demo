import asyncio
import json
import logging
from typing import Dict, List
from mcp.client.session import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult

from core.config import settings
from core.exceptions import MCPConnectionError, MCPToolNotFoundError
from models.mcp import MCPServerConfig, MCPToolInfo

logger = logging.getLogger(__name__)


class MCPClient:
    def __init__(self):
        self.servers: Dict[str, MCPServerConfig] = {}
        self.all_tools: List[MCPToolInfo] = []
    
    def load_config(self):
        with open(settings.MCP_CONFIG_PATH, "r", encoding="utf-8") as f:
            config = json.load(f)
            
            self.servers.clear()
            for name, server_config in config.get("mcpServers", {}).items():
                self.servers[name] = MCPServerConfig(
                    name=name,
                    url=server_config.get("url", ""),
                    description=server_config.get("description", "")
                )
    
    async def get_tools_from_server(self, server: str, config: MCPServerConfig) -> List[MCPToolInfo]:
        try:
            async with streamable_http_client(config.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.list_tools()
                    
                    tool_list = []
                    for item in result.tools:
                        tool = MCPToolInfo(
                            server=server,
                            name=item.name,
                            description=item.description or "无描述",
                            input_schema=item.inputSchema or {"type": "object", "properties": {}}
                        )
                        tool_list.append(tool)
                    return tool_list
        except Exception as e:
            logger.warning(f"Failed to connect to MCP server {server}: {e}")
            return []
    
    async def load_all_tools(self):
        tasks = [
            self.get_tools_from_server(server, config)
            for server, config in self.servers.items()
        ]
        result = await asyncio.gather(*tasks)
        
        self.all_tools.clear()
        for tool_list in result:
            self.all_tools.extend(tool_list)
    
    async def call_tool(self, server: str, tool_name: str, params: Dict) -> CallToolResult:
        config = self.servers.get(server)
        if not config:
            raise MCPToolNotFoundError(f"MCP server '{server}' not found")
        
        try:
            async with streamable_http_client(config.url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool(tool_name, params)
                    return result
        except Exception as e:
            raise MCPConnectionError(f"Failed to call tool {tool_name} on server {server}: {e}")


mcp_client = MCPClient()
