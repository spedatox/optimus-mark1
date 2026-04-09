"""MCP manager — stub that will be replaced with full MCP client implementation."""
from __future__ import annotations
from typing import Any

_manager: "MCPManager | None" = None


class MCPManager:
    """Manages connections to MCP servers and proxies tool/resource calls."""

    def __init__(self) -> None:
        self._servers: dict[str, Any] = {}

    async def list_resources(self, server_filter: str | None = None) -> list[dict]:
        results = []
        for server_name, client in self._servers.items():
            if server_filter and server_name != server_filter:
                continue
            try:
                resources = await client.list_resources()
                for r in resources:
                    results.append({
                        "uri": r.uri,
                        "name": r.name,
                        "mimeType": getattr(r, "mimeType", None),
                        "description": getattr(r, "description", None),
                        "server": server_name,
                    })
            except Exception:
                pass
        return results

    async def read_resource(self, server: str, uri: str) -> list[dict]:
        client = self._servers.get(server)
        if client is None:
            raise ValueError(f"MCP server '{server}' not connected.")
        result = await client.read_resource(uri)
        contents = []
        for item in result.contents:
            contents.append({
                "uri": item.uri,
                "mimeType": getattr(item, "mimeType", None),
                "text": getattr(item, "text", None),
            })
        return contents

    async def call_tool(self, server: str, tool_name: str, arguments: dict) -> Any:
        client = self._servers.get(server)
        if client is None:
            raise ValueError(f"MCP server '{server}' not connected.")
        return await client.call_tool(tool_name, arguments)

    async def start_auth(self, server: str) -> str:
        client = self._servers.get(server)
        if client is None:
            raise ValueError(f"MCP server '{server}' not connected.")
        return await client.start_auth()

    async def complete_auth(self, server: str, code: str) -> None:
        client = self._servers.get(server)
        if client is None:
            raise ValueError(f"MCP server '{server}' not connected.")
        await client.complete_auth(code)

    async def get_auth_status(self, server: str) -> str:
        client = self._servers.get(server)
        if client is None:
            return "not_connected"
        return await client.get_auth_status()

    def register_server(self, name: str, client: Any) -> None:
        self._servers[name] = client

    def get_server_names(self) -> list[str]:
        return list(self._servers.keys())


def get_mcp_manager() -> MCPManager:
    global _manager
    if _manager is None:
        _manager = MCPManager()
    return _manager
