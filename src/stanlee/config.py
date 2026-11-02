"""Generate client configuration without modifying existing settings."""
import copy
import os
from pathlib import Path

from .errors import StanleeError


def generate(client: str, python: str, workspaces: list[str], discovery: str,
             application: str | None = None, existing: dict | None = None) -> dict:
    if not Path(python).is_absolute():
        raise StanleeError("invalid_arguments", "Use an absolute Python executable path")
    arguments = ["-m", "stanlee.cli"]
    for workspace in workspaces:
        if not Path(workspace).is_absolute():
            raise StanleeError("invalid_arguments", "Workspace grants must be absolute")
        arguments += ["--workspace", workspace]
    arguments += ["--discovery-dir", discovery]
    if application:
        arguments += ["--application", application]
    arguments.append("serve")
    if client == "codex":
        return {"argv": ["codex", "mcp", "add", "stanlee", "--", python, *arguments],
                "note": "Run using Codex's official config command. Existing unrelated settings are preserved by Codex."}
    if client not in {"cursor", "claude-desktop"}:
        raise StanleeError("invalid_arguments", "Unknown client")
    configuration = copy.deepcopy(existing or {})
    servers = configuration.setdefault("mcpServers", {})
    if not isinstance(servers, dict) or "stanlee" in servers:
        raise StanleeError("config_conflict", "Existing Stanlee entry or invalid server table; no settings changed")
    servers["stanlee"] = {"command": python, "args": arguments}
    return configuration
