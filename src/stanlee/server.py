"""Official MCP SDK adapter. Native commands use the same Service as the CLI."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from . import __version__
from .errors import StanleeError
from .registry import REGISTRY, OPERATIONS
from .service import Service


def create_server(service: Service) -> MCPServer:
    @asynccontextmanager
    async def lifespan(_server):
        try:
            yield service
        finally:
            if service._jobs is not None:
                await asyncio.to_thread(service._jobs.close)

    server = MCPServer("Stanlee", version=__version__, subscriptions=False, lifespan=lifespan,
        instructions="Inspect before editing. Use the returned document_id and revision on every mutation. "
        "On stale_revision, inspect again and reconcile the human's changes. Only advertised native operations are available. "
        "This development build is not a qualified alpha; full editor coverage is pending. "
        "edit.batch accepts only advertised undoable document operations. Files, settings, history and nested batches are excluded. "
        "Checkpoints recover content as a new document, invalidating old handles and history.")

    async def run(function, *args, **kwargs):
        try:
            return await asyncio.to_thread(function, *args, **kwargs)
        except StanleeError as error:
            raise ToolError(json.dumps(error.as_dict())) from error

    read = ToolAnnotations(read_only_hint=True, destructive_hint=False, open_world_hint=False)
    write = ToolAnnotations(read_only_hint=False, destructive_hint=True, open_world_hint=False)

    @server.tool(annotations=read)
    async def sessions() -> list[dict]:
        """Discover explicitly enabled native sessions; credentials are never returned."""
        return await run(service.sessions)

    @server.tool(annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    async def launch() -> dict:
        """Launch the configured bridge build with this server's explicit workspace grants."""
        return await run(service.launch)

    @server.tool(structured_output=True, annotations=read)
    async def inspect_document(session_id: str) -> dict[str, Any]:
        """Read native layers, frames, FPS, selection, dirty state and revision."""
        return await run(service.inspect, session_id)

    @server.tool(structured_output=True, annotations=write)
    async def command(session_id: str, operation: str, arguments: dict,
                      expected_revision: int | None = None, document_id: str | None = None) -> dict[str, Any]:
        """Execute a typed native operation from stanlee://operations with revision conflict checks."""
        return await run(service.command, session_id, operation, arguments, expected_revision, document_id)

    @server.tool(annotations=read)
    async def preview(session_id: str, frame: int | None = None, camera_index: int | None = None) -> Image:
        """Render a PNG through native composition and camera transforms."""
        arguments = {key: value for key, value in {"frame": frame, "camera_index": camera_index}.items() if value is not None}
        result = await run(service.command, session_id, "frame.preview", arguments)
        return Image(data=base64.b64decode(result["data"], validate=True), format="png")

    @server.tool(annotations=read)
    async def diagnostics() -> dict:
        """Inspect the application and environment without returning tokens."""
        return await run(service.diagnostics)

    @server.tool(structured_output=True, annotations=write)
    async def export_saved_project(input_path: str, outputs: list[str], camera: str | None = None,
                                   width: int | None = None, height: int | None = None, start: int = 1,
                                   end: str = "last", transparency: bool = False, overwrite: bool = False,
                                   timeout: float = 120) -> dict[str, Any]:
        """Queue native export of a saved project; poll the job until validated output succeeds."""
        from .export import ExportOptions
        options = ExportOptions(input_path, outputs, camera, width, height, start, end, transparency, overwrite, timeout)
        return await run(service.jobs.submit, options)

    @server.tool(structured_output=True, annotations=write)
    async def export_document(session_id: str, expected_revision: int, document_id: str, outputs: list[str],
                              fps: int | None = None, camera: str | None = None, width: int | None = None,
                              height: int | None = None, start: int = 1, end: str = "last", transparency: bool = False,
                              overwrite: bool = False, timeout: float = 120) -> dict[str, Any]:
        """Snapshot unsaved native content without changing the active document, then queue native export.

        An FPS override changes only the independent snapshot. Poll job_status
        until validation succeeds. Snapshot files are retained for recovery.
        """
        return await run(service.export_document, session_id, expected_revision, document_id, outputs,
                         fps=fps, camera=camera, width=width, height=height, start=start, end=end,
                         transparency=transparency, overwrite=overwrite, timeout=timeout)

    @server.tool(structured_output=True, annotations=read)
    async def job_status(job_id: str) -> dict[str, Any]:
        """Read persistent queued/running/succeeded/failed/cancelled/interrupted job evidence."""
        return await run(service.jobs.get, job_id)

    @server.tool(structured_output=True, annotations=ToolAnnotations(read_only_hint=False, destructive_hint=False, open_world_hint=False))
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Request cancellation of a worker owned by this service."""
        return await run(service.jobs.cancel, job_id)

    @server.tool(structured_output=True, annotations=write)
    async def recover_outputs(directories: list[str]) -> dict[str, Any]:
        """Recover interrupted publications in explicit granted output directories.

        Refuse live publishers. Restore original output bytes or retain validated
        committed outputs; preserve external edits and report retained backups.
        """
        return await run(service.recover_outputs, directories)

    @server.resource("stanlee://jobs", mime_type="application/json")
    async def jobs_resource() -> str:
        return json.dumps(await run(service.jobs.list))

    @server.resource("stanlee://jobs/{job_id}", mime_type="application/json")
    async def job_resource(job_id: str) -> str:
        return json.dumps(await run(service.jobs.get, job_id))

    @server.resource("stanlee://operations", mime_type="application/json")
    def operations() -> str:
        return json.dumps(REGISTRY)

    @server.resource("stanlee://operations/{operation}", mime_type="application/json")
    def operation_contract(operation: str) -> str:
        if operation not in OPERATIONS:
            raise ValueError("Unknown operation")
        return json.dumps(OPERATIONS[operation])

    @server.resource("stanlee://sessions", mime_type="application/json")
    async def session_resource() -> str:
        return json.dumps(await run(service.sessions))

    @server.resource("stanlee://documents/{session_id}", mime_type="application/json")
    async def document_resource(session_id: str) -> str:
        return json.dumps(await run(service.inspect, session_id))

    @server.resource("stanlee://layers/{session_id}", mime_type="application/json")
    async def layers_resource(session_id: str) -> str:
        return json.dumps((await run(service.inspect, session_id))["layers"])

    @server.resource("stanlee://timeline/{session_id}", mime_type="application/json")
    async def timeline_resource(session_id: str) -> str:
        state = await run(service.inspect, session_id)
        return json.dumps({key: state[key] for key in ("frame", "fps", "layers", "revision")})

    @server.resource("stanlee://palettes/{session_id}", mime_type="application/json")
    async def palette_resource(session_id: str) -> str:
        return json.dumps(await run(service.command, session_id, "palette.inspect", {}))

    @server.prompt()
    def inspect_animation() -> str:
        return "Discover sessions, inspect native state and preview the current frame. Explain layers, timing and unsaved state before proposing edits."

    @server.prompt()
    def create_animation() -> str:
        return "Inspect capabilities and the current document. Create a new document only with explicit discard if needed. Use advertised native layer, stroke and timeline operations. Reinspect after conflicts. Save to a granted path and verify a native preview."

    @server.prompt()
    def repair_animation() -> str:
        return "Inspect layers, timeline and preview. Diagnose the smallest repair. Preserve human changes and use current revisions. Use document.checkpoint before risky workflows. Use edit.batch only for operations whose contract advertises native_document_transaction; file writes, settings and nested batches are excluded. Recovery requires explicit discard and invalidates prior history and handles."

    @server.prompt()
    def export_animation() -> str:
        return "Inspect native state and capabilities. Export unsaved content with export_document using the current document_id and revision. FPS overrides apply only to the snapshot. Poll the job; verify content, dimensions, timing and audio before accepting the result."

    return server
