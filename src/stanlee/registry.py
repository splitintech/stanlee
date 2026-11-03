"""Shared command contracts packaged with the Python service and native bridge."""
import json
from importlib.resources import files

from jsonschema import Draft202012Validator

from .errors import StanleeError

REGISTRY = json.loads(files("stanlee").joinpath("operations.json").read_text())
OPERATIONS = {item["id"]: item for item in REGISTRY["operations"]}


def validate(operation: str, arguments: dict) -> dict:
    if operation not in OPERATIONS:
        raise StanleeError("unsupported_capability", "Operation is not implemented in this build")
    contract = OPERATIONS[operation]
    errors = list(Draft202012Validator(contract["input"]).iter_errors(arguments))
    if errors:
        raise StanleeError("invalid_arguments", errors[0].message)
    if operation == "edit.batch":
        samples = 0
        for step in arguments["operations"]:
            nested = OPERATIONS.get(step["operation"], {})
            if step["operation"] == "edit.batch" or nested.get("undo") != "native_document_transaction":
                raise StanleeError("unsupported_atomic_operation", "Batch accepts undoable document edits only")
            validate(step["operation"], step["arguments"])
            if step["operation"] == "canvas.stroke":
                samples += len(step["arguments"]["points"])
        if samples > 16384:
            raise StanleeError("invalid_arguments", "Batch exceeds 16384 native pointer samples")
    # JSON Schema considers NaN a number; the wire encoder must never emit it.
    try:
        json.dumps(arguments, allow_nan=False)
    except (ValueError, TypeError) as exc:
        raise StanleeError("invalid_arguments", "Arguments must contain finite JSON values") from exc
    return contract
