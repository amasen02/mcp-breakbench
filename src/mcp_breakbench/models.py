from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

Json = Any


class Outcome(StrEnum):
    PASS = "PASS"
    SAFE_SKIP_NOT_ALLOWLISTED = "SAFE_SKIP_NOT_ALLOWLISTED"
    SAFE_SKIP_TOOL_MISSING = "SAFE_SKIP_TOOL_MISSING"
    INPUT_SCHEMA_INVALID = "INPUT_SCHEMA_INVALID"
    INPUT_VALIDATION_FAILED = "INPUT_VALIDATION_FAILED"
    TOOL_RESULT_ERROR = "TOOL_RESULT_ERROR"
    OUTPUT_SCHEMA_INVALID = "OUTPUT_SCHEMA_INVALID"
    OUTPUT_SCHEMA_MISMATCH = "OUTPUT_SCHEMA_MISMATCH"
    SDK_OUTPUT_SCHEMA_REJECTED = "SDK_OUTPUT_SCHEMA_REJECTED"
    CALL_TIMEOUT = "CALL_TIMEOUT"
    PROTOCOL_ERROR = "PROTOCOL_ERROR"
    TRANSPORT_ERROR = "TRANSPORT_ERROR"
    CLIENT_RUNTIME_ERROR = "CLIENT_RUNTIME_ERROR"


@dataclass(frozen=True)
class ServerSpec:
    command: str
    args: tuple[str, ...]
    cwd: str | None = None
    env: dict[str, str] | None = None


@dataclass(frozen=True)
class Limits:
    initialization_timeout_seconds: float = 5.0
    discovery_timeout_seconds: float = 5.0
    default_timeout_seconds: float = 2.0
    max_cases: int = 25
    max_tool_pages: int = 20
    max_tools: int = 500
    max_output_bytes: int = 65_536
    max_stderr_bytes: int = 16_384


@dataclass(frozen=True)
class CaseSpec:
    id: str
    tool: str
    arguments: dict[str, Json]
    timeout_seconds: float | None = None


@dataclass(frozen=True)
class RunSpec:
    server: ServerSpec
    allow_tools: frozenset[str]
    cases: tuple[CaseSpec, ...]
    limits: Limits
    redaction_values: tuple[str, ...] = ()


@dataclass(frozen=True)
class ToolContract:
    name: str
    title: str | None
    description: str | None
    input_schema: dict[str, Json]
    output_schema: dict[str, Json] | None
    annotations: dict[str, Json] | None

    def to_dict(self) -> dict[str, Json]:
        return asdict(self)


@dataclass(frozen=True)
class DriftFinding:
    kind: str
    tool: str
    details: Json = None


@dataclass(frozen=True)
class CaseReceipt:
    id: str
    tool: str
    outcome: Outcome
    detail: str
    arguments: Json = None
    content: Json = None
    structured_content: Json = None


@dataclass
class BenchReport:
    schema_version: str = "1"
    server: str = ""
    tools: list[dict[str, Json]] = field(default_factory=list)
    drift: list[DriftFinding] = field(default_factory=list)
    cases: list[CaseReceipt] = field(default_factory=list)
    stderr: str = ""
    system_error: dict[str, str] | None = None
    connections_opened: int = 0
    session_restarts: int = 0

    def to_dict(self) -> dict[str, Json]:
        return asdict(self)

    @property
    def has_failures(self) -> bool:
        nonfailures = {Outcome.PASS, Outcome.SAFE_SKIP_NOT_ALLOWLISTED}
        return bool(self.drift or self.system_error) or any(
            case.outcome not in nonfailures for case in self.cases
        )
