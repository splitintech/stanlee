import asyncio
import json

from mcp.client import Client

from stanlee.server import create_server
from stanlee.service import Service


def test_official_sdk_negotiates_tools_resources_prompts_and_errors(tmp_path):
    service = Service([str(tmp_path)], tmp_path/"sessions")
    async def scenario():
        async with Client(create_server(service)) as client:
            tools = await client.list_tools()
            assert "command" in {tool.name for tool in tools.tools}
            by_name = {tool.name: tool for tool in tools.tools}
            for name in ("sessions", "inspect_document", "preview", "diagnostics", "job_status"):
                assert by_name[name].annotations.read_only_hint is True
            for name in ("command", "export_saved_project", "export_document"):
                assert by_name[name].annotations.read_only_hint is False
                assert by_name[name].annotations.destructive_hint is True
            result = await client.call_tool("sessions", {})
            assert not result.is_error
            resources = await client.list_resources()
            assert any(str(item.uri) == "stanlee://operations" for item in resources.resources)
            prompts = await client.list_prompts()
            assert len(prompts.prompts) == 4
            failure = await client.call_tool("command", {"session_id": "missing", "operation": "project.fps", "arguments": {"fps": 12}})
            assert failure.is_error
            assert "revision_required" in str(failure)
    asyncio.run(scenario())
