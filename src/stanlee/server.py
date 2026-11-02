"""Official MCP SDK adapter. Native commands use the same Service as the CLI."""
import asyncio
import base64
import json
from contextlib import asynccontextmanager
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver import Image
from mcp.server.mcpserver.exceptions import ToolError

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
        "This development build is not a qualified alpha; pressure, atomic batches, recovery workflows and full editor coverage are pending.")

    async def run(function, *args, **kwargs):
        try:
            return await asyncio.to_thread(function, *args, **kwargs)
        except StanleeError as error:
            raise ToolError(json.dumps(error.as_dict())) from error

    @server.tool()
    async def sessions() -> list[dict]:
        """Discover explicitly enabled native sessions; credentials are never returned."""
        return await run(service.sessions)

    @server.tool()
    async def launch() -> dict:
        """Launch the configured bridge build with this server's explicit workspace grants."""
        return await run(service.launch)

    @server.tool(structured_output=True)
    async def inspect_document(session_id: str) -> dict[str, Any]:
        """Read native layers, frames, FPS, selection, dirty state and revision."""
        return await run(service.inspect, session_id)

    @server.tool(structured_output=True)
    async def command(session_id: str, operation: str, arguments: dict,
                      expected_revision: int | None = None, document_id: str | None = None) -> dict[str, Any]:
        """Execute a typed native operation from stanlee://operations with revision conflict checks."""
        return await run(service.command, session_id, operation, arguments, expected_revision, document_id)

    @server.tool()
    async def preview(session_id: str, frame: int | None = None) -> Image:
        """Render a PNG through native composition and camera transforms."""
        result = await run(service.command, session_id, "frame.preview", {} if frame is None else {"frame": frame})
        return Image(data=base64.b64decode(result["data"], validate=True), format="png")

    @server.tool()
    async def diagnostics() -> dict:
        """Inspect the application and environment without returning tokens."""
        return await run(service.diagnostics)

    @server.tool(structured_output=True)
    async def export_saved_project(input_path: str, outputs: list[str], camera: str | None = None,
                                   width: int | None = None, height: int | None = None, start: int = 1,
                                   end: str = "last", transparency: bool = False, overwrite: bool = False,
                                   timeout: float = 120) -> dict[str, Any]:
        """Queue native export of a saved project; poll the job until validated output succeeds."""
        from .export import ExportOptions
        options = ExportOptions(input_path, outputs, camera, width, height, start, end, transparency, overwrite, timeout)
        return await run(service.jobs.submit, options)

    @server.tool(structured_output=True)
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

    @server.tool(structured_output=True)
    async def job_status(job_id: str) -> dict[str, Any]:
        """Read persistent queued/running/succeeded/failed/cancelled/interrupted job evidence."""
        return await run(service.jobs.get, job_id)

    @server.tool(structured_output=True)
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Request cancellation of a worker owned by this service."""
        return await run(service.jobs.cancel, job_id)

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

    @server.prompt()
    def inspect_animation() -> str:
        return "Discover sessions, inspect native state and preview the current frame. Explain layers, timing and unsaved state before proposing edits."

    @server.prompt()
    def create_animation() -> str:
        return "Inspect capabilities and the current document. Create a new document only with explicit discard if needed. Use advertised native layer, stroke and timeline operations. Reinspect after conflicts. Save to a granted path and verify a native preview."

    @server.prompt()
    def repair_animation() -> str:
        return "Inspect layers, timeline and preview. Diagnose the smallest repair. Preserve human changes, use current revisions, and use native undo for operations whose contract supports it. Do not assume checkpoint or batch support."

    @server.prompt()
    def export_animation() -> str:
        return "Inspect native state and capabilities. Export unsaved content with export_document using the current document_id and revision. FPS overrides apply only to the snapshot. Poll the job; verify content, dimensions, timing and audio before accepting the result."

    return server
