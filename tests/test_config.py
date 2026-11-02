import asyncio
import json
import sys
from pathlib import Path

import pytest
from mcp.client import Client
from mcp.client.stdio import StdioServerParameters

from stanlee.config import generate
from stanlee.errors import StanleeError


def test_json_merge_preserves_other_settings_and_rejects_conflict(tmp_path):
    original = {"mcpServers": {"existing": {"command": "keep"}}, "theme": "dark"}
    result = generate("cursor", sys.executable, [str(tmp_path)], str(tmp_path/"sessions"), existing=original)
    assert result["theme"] == "dark"
    assert result["mcpServers"]["existing"] == original["mcpServers"]["existing"]
    assert "stanlee" not in original["mcpServers"]
    with pytest.raises(StanleeError, match="config_conflict"):
        generate("cursor", sys.executable, [str(tmp_path)], str(tmp_path/"sessions"), existing=result)


def test_generated_stdio_configuration_with_official_client(tmp_path):
    configuration = generate("claude-desktop", sys.executable, [str(tmp_path)], str(tmp_path/"sessions"))["mcpServers"]["stanlee"]
    async def scenario():
        async with Client(StdioServerParameters(**configuration)) as client:
            result = await client.call_tool("sessions", {})
            assert not result.is_error
            tools = await client.list_tools()
            assert "command" in {tool.name for tool in tools.tools}
    asyncio.run(scenario())
