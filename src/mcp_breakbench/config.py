from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from .models import CaseSpec, Limits, RunSpec, ServerSpec

MAX_TIMEOUT = 30.0
MAX_CASES = 100
MAX_TOOL_PAGES = 100
MAX_TOOLS = 10_000
MAX_BYTES = 1_048_576


class ConfigError(ValueError):
    pass


def _object(value: Any, where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be an object")
    return cast(dict[str, Any], value)


def _float(raw: dict[str, Any], key: str, default: float) -> float:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConfigError(f"limits.{key} must be a number")
    return float(value)


def _int(raw: dict[str, Any], key: str, default: int) -> int:
    value = raw.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ConfigError(f"limits.{key} must be an integer")
    return cast(int, value)


def load_run_spec(path: Path) -> RunSpec:
    try:
        raw = _object(json.loads(path.read_text(encoding="utf-8")), "config")
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigError(f"cannot read config: {exc}") from exc
    server_raw = _object(raw.get("server"), "server")
    command = server_raw.get("command")
    args = server_raw.get("args", [])
    if not isinstance(command, str) or not command.strip():
        raise ConfigError("server.command must be a non-empty string")
    if not isinstance(args, list) or not all(isinstance(x, str) for x in args):
        raise ConfigError("server.args must be an array of strings")
    cwd_raw = server_raw.get("cwd")
    cwd: str | None = None
    if cwd_raw is not None:
        if not isinstance(cwd_raw, str):
            raise ConfigError("server.cwd must be a string")
        cwd = str((path.parent / cwd_raw).resolve()) if not Path(cwd_raw).is_absolute() else cwd_raw
    env_raw = server_raw.get("env")
    if env_raw is not None and (
        not isinstance(env_raw, dict)
        or not all(isinstance(k, str) and isinstance(v, str) for k, v in env_raw.items())
    ):
        raise ConfigError("server.env must contain string keys and values")

    limits_raw = _object(raw.get("limits", {}), "limits")
    limits = Limits(
        initialization_timeout_seconds=_float(limits_raw, "initialization_timeout_seconds", 5.0),
        discovery_timeout_seconds=_float(limits_raw, "discovery_timeout_seconds", 5.0),
        default_timeout_seconds=_float(limits_raw, "default_timeout_seconds", 2.0),
        max_cases=_int(limits_raw, "max_cases", 25),
        max_tool_pages=_int(limits_raw, "max_tool_pages", 20),
        max_tools=_int(limits_raw, "max_tools", 500),
        max_output_bytes=_int(limits_raw, "max_output_bytes", 65_536),
        max_stderr_bytes=_int(limits_raw, "max_stderr_bytes", 16_384),
    )
    if not 0 < limits.initialization_timeout_seconds <= MAX_TIMEOUT:
        raise ConfigError(f"initialization timeout must be in (0, {MAX_TIMEOUT}]")
    if not 0 < limits.discovery_timeout_seconds <= MAX_TIMEOUT:
        raise ConfigError(f"discovery timeout must be in (0, {MAX_TIMEOUT}]")
    if not 0 < limits.default_timeout_seconds <= MAX_TIMEOUT:
        raise ConfigError(f"default timeout must be in (0, {MAX_TIMEOUT}]")
    if not 0 < limits.max_cases <= MAX_CASES:
        raise ConfigError(f"max_cases must be in [1, {MAX_CASES}]")
    if not 0 < limits.max_tool_pages <= MAX_TOOL_PAGES:
        raise ConfigError(f"max_tool_pages must be in [1, {MAX_TOOL_PAGES}]")
    if not 0 < limits.max_tools <= MAX_TOOLS:
        raise ConfigError(f"max_tools must be in [1, {MAX_TOOLS}]")
    if not 0 < limits.max_output_bytes <= MAX_BYTES or not 0 < limits.max_stderr_bytes <= MAX_BYTES:
        raise ConfigError(f"output limits must be in [1, {MAX_BYTES}]")

    allow = raw.get("allow_tools", [])
    if not isinstance(allow, list) or not all(isinstance(x, str) and x for x in allow):
        raise ConfigError("allow_tools must be an array of non-empty strings")
    cases_raw = raw.get("cases", [])
    if not isinstance(cases_raw, list) or len(cases_raw) > limits.max_cases:
        raise ConfigError("cases must be an array no larger than max_cases")
    cases: list[CaseSpec] = []
    ids: set[str] = set()
    for index, value in enumerate(cases_raw):
        case = _object(value, f"cases[{index}]")
        case_id, tool, arguments = case.get("id"), case.get("tool"), case.get("arguments")
        if not isinstance(case_id, str) or not case_id or case_id in ids:
            raise ConfigError("case IDs must be unique non-empty strings")
        if not isinstance(tool, str) or not tool or not isinstance(arguments, dict):
            raise ConfigError(f"case {case_id} needs a non-empty tool and object arguments")
        timeout = case.get("timeout_seconds")
        if timeout is not None and (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or not 0 < timeout <= MAX_TIMEOUT
        ):
            raise ConfigError(f"case {case_id} timeout must be in (0, {MAX_TIMEOUT}]")
        ids.add(case_id)
        cases.append(CaseSpec(case_id, tool, arguments, float(timeout) if timeout else None))

    redact_raw = _object(raw.get("redaction", {}), "redaction")
    extra = redact_raw.get("extra_values", [])
    if not isinstance(extra, list) or not all(isinstance(x, str) for x in extra):
        raise ConfigError("redaction.extra_values must be an array of strings")
    return RunSpec(
        ServerSpec(command, tuple(args), cwd, dict(env_raw) if env_raw else None),
        frozenset(allow),
        tuple(cases),
        limits,
        tuple(x for x in extra if x),
    )
