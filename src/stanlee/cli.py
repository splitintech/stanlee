"""Stanlee command line; machine-readable JSON on stdout, errors on stderr."""
import argparse
import json
import sys
import time
from pathlib import Path

from .errors import StanleeError
from .registry import REGISTRY
from .service import Service


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="Native Pencil2D automation (experimental development build)")
    root.add_argument("--workspace", action="append", default=[], help="Explicit granted directory; repeat for multiple grants")
    root.add_argument("--discovery-dir", type=Path, default=Path.home()/".local/state/stanlee/sessions")
    root.add_argument("--application", help="Native Pencil2D executable")
    sub = root.add_subparsers(dest="action", required=True)
    for name in ("serve", "diagnostics", "sessions", "launch", "operations"):
        sub.add_parser(name)
    inspect = sub.add_parser("inspect")
    inspect.add_argument("session_id")
    command = sub.add_parser("command")
    command.add_argument("session_id")
    command.add_argument("operation")
    command.add_argument("--arguments", type=json.loads, default={})
    command.add_argument("--expected-revision", type=int)
    command.add_argument("--document-id")
    export = sub.add_parser("export")
    export.add_argument("input")
    export.add_argument("--export", "-o", "--export-sequence", action="append", dest="outputs", required=True)
    export.add_argument("--camera")
    export.add_argument("--width", type=int)
    export.add_argument("--height", type=int)
    export.add_argument("--start", type=int, default=1)
    export.add_argument("--end", default="last")
    export.add_argument("--transparency", action="store_true")
    export.add_argument("--overwrite", action="store_true")
    export.add_argument("--timeout", type=float, default=120)
    jobs = sub.add_parser("jobs")
    jobs.add_argument("job_id", nargs="?")
    config = sub.add_parser("config")
    config.add_argument("--client", choices=["codex", "cursor", "claude-desktop"], required=True)
    config.add_argument("--python", default=sys.executable)
    config.add_argument("--existing", type=Path, help="Read an existing JSON config and print the merged result")
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.action == "config":
            from .config import generate
            existing = json.loads(args.existing.read_text()) if args.existing else None
            result = generate(args.client, args.python, args.workspace, str(args.discovery_dir), args.application, existing)
        elif args.action == "operations":
            result = REGISTRY
        else:
            service = Service(args.workspace, args.discovery_dir, executable=args.application)
            if args.action == "serve":
                from .server import create_server
                create_server(service).run(transport="stdio")
                return 0
            if args.action in {"diagnostics", "sessions", "launch"}:
                result = getattr(service, args.action)()
            elif args.action == "inspect":
                result = service.inspect(args.session_id)
            elif args.action == "jobs":
                result = service.jobs.get(args.job_id) if args.job_id else service.jobs.list()
            elif args.action == "export":
                from .export import ExportOptions
                options = ExportOptions(**{key: getattr(args, key) for key in ExportOptions.__dataclass_fields__})
                result = service.jobs.submit(options)
                try:
                    while result["state"] in {"queued", "running"}:
                        time.sleep(.1)
                        result = service.jobs.get(result["job_id"])
                finally:
                    service.jobs.close()
                if result["state"] != "succeeded":
                    raise StanleeError(result["state"], "Export job did not succeed", result)
            else:
                result = service.command(args.session_id, args.operation, args.arguments,
                                         args.expected_revision, args.document_id)
        print(json.dumps(result, ensure_ascii=False, allow_nan=False))
        return 0
    except StanleeError as error:
        print(json.dumps({"error": error.as_dict()}), file=sys.stderr)
        return 2
    except (OSError, ValueError) as error:
        print(json.dumps({"error": {"code": "local_failure", "message": str(error)}}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
