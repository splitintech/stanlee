"""Structured application errors remain distinct from transport failures."""
from dataclasses import dataclass, field
from typing import Any


@dataclass
class StanleeError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"

    def as_dict(self) -> dict:
        return {"code": self.code, "message": self.message, "details": self.details}


class TransportError(StanleeError):
    def __init__(self, message: str):
        super().__init__("transport_failure", message)
