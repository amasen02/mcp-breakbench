from __future__ import annotations

from typing import Any

import anyio
from mcp import MCPError

from .client import DiscoveryLimitError, InitializationTimeoutError, discover_tools, open_session
from .models import BenchReport, CaseReceipt, Outcome, RunSpec
from .redaction import BoundedTextCapture, Redactor, bound_value
from .schemas import validate_instance, validate_schema
from .snapshot import diff_snapshots, make_snapshot


def _clean(redactor: Redactor, value: Any, limit: int) -> Any:
    return bound_value(redactor.value(value), limit)


def _exception_kind(exc: BaseException) -> Outcome:
    text = str(exc).lower()
    if isinstance(exc, MCPError):
        return Outcome.CALL_TIMEOUT if "timed out" in text else Outcome.PROTOCOL_ERROR
    if isinstance(exc, TimeoutError):
        return Outcome.CALL_TIMEOUT
    if isinstance(exc, (anyio.BrokenResourceError, anyio.ClosedResourceError, anyio.EndOfStream)):
        return Outcome.TRANSPORT_ERROR
    if isinstance(exc, RuntimeError) and str(exc).startswith(
        "Invalid structured content returned by tool"
    ):
        return Outcome.SDK_OUTPUT_SCHEMA_REJECTED
    return Outcome.CLIENT_RUNTIME_ERROR


def _contains_exception(exc: BaseException, kind: type[BaseException]) -> bool:
    if isinstance(exc, kind):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_exception(child, kind) for child in exc.exceptions)
    return False


def _contains_runtime_message(exc: BaseException, prefix: str) -> bool:
    if isinstance(exc, RuntimeError) and str(exc).startswith(prefix):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_contains_runtime_message(child, prefix) for child in exc.exceptions)
    return False


def _exception_details(exc: BaseException) -> str:
    if isinstance(exc, BaseExceptionGroup):
        details = [_exception_details(child) for child in exc.exceptions]
        return "; ".join(dict.fromkeys(detail for detail in details if detail))
    return str(exc) or type(exc).__name__


async def run_bench(spec: RunSpec, baseline: dict[str, Any] | None = None) -> BenchReport:
    redactor = Redactor(spec.redaction_values)
    errlog = BoundedTextCapture(spec.limits.max_stderr_bytes, redactor)
    report = BenchReport(server="configured stdio server", connections_opened=1)
    try:
        async with open_session(
            spec.server, errlog, spec.limits.initialization_timeout_seconds
        ) as session:
            try:
                with anyio.fail_after(spec.limits.discovery_timeout_seconds):
                    tools = await discover_tools(
                        session, spec.limits.max_tool_pages, spec.limits.max_tools
                    )
            except TimeoutError as exc:
                raise TimeoutError("MCP tool discovery timed out") from exc
            current_snapshot = redactor.value(make_snapshot(tools))
            report.tools = current_snapshot["tools"]
            if baseline is not None:
                report.drift = diff_snapshots(baseline, current_snapshot)
            for case in spec.cases:
                arguments = _clean(redactor, case.arguments, spec.limits.max_output_bytes)
                if case.tool not in spec.allow_tools:
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            Outcome.SAFE_SKIP_NOT_ALLOWLISTED,
                            "tool not in explicit allowlist",
                            arguments,
                        )
                    )
                    continue
                tool = tools.get(case.tool)
                if tool is None:
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            Outcome.SAFE_SKIP_TOOL_MISSING,
                            "tool was not discovered",
                            arguments,
                        )
                    )
                    continue
                schema_problem = validate_schema(tool.input_schema)
                if schema_problem:
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            Outcome.INPUT_SCHEMA_INVALID,
                            redactor.text(schema_problem),
                            arguments,
                        )
                    )
                    continue
                input_errors = validate_instance(tool.input_schema, case.arguments)
                if input_errors:
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            Outcome.INPUT_VALIDATION_FAILED,
                            redactor.text("; ".join(input_errors)),
                            arguments,
                        )
                    )
                    continue
                if tool.output_schema is not None:
                    schema_problem = validate_schema(tool.output_schema)
                    if schema_problem:
                        report.cases.append(
                            CaseReceipt(
                                case.id,
                                case.tool,
                                Outcome.OUTPUT_SCHEMA_INVALID,
                                redactor.text(schema_problem),
                                arguments,
                            )
                        )
                        continue
                try:
                    result = await session.call_tool(
                        case.tool,
                        arguments=case.arguments,
                        read_timeout_seconds=case.timeout_seconds
                        or spec.limits.default_timeout_seconds,
                    )
                    content = [
                        block.model_dump(mode="json", by_alias=True, exclude_none=True)
                        for block in result.content
                    ]
                    clean_content = _clean(redactor, content, spec.limits.max_output_bytes)
                    clean_structured = _clean(
                        redactor, result.structured_content, spec.limits.max_output_bytes
                    )
                    if result.is_error:
                        outcome, detail = Outcome.TOOL_RESULT_ERROR, "server returned isError=true"
                    elif tool.output_schema is not None:
                        errors = validate_instance(tool.output_schema, result.structured_content)
                        outcome = Outcome.OUTPUT_SCHEMA_MISMATCH if errors else Outcome.PASS
                        detail = (
                            redactor.text("; ".join(errors)) if errors else "contract satisfied"
                        )
                    else:
                        outcome, detail = Outcome.PASS, "contract satisfied"
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            outcome,
                            detail,
                            arguments,
                            clean_content,
                            clean_structured,
                        )
                    )
                except Exception as exc:
                    report.cases.append(
                        CaseReceipt(
                            case.id,
                            case.tool,
                            _exception_kind(exc),
                            redactor.text(str(exc)),
                            arguments,
                        )
                    )
    except Exception as exc:
        text = redactor.text(_exception_details(exc))
        if _contains_exception(exc, InitializationTimeoutError):
            system_kind = "INITIALIZATION_TIMEOUT"
        elif _contains_exception(exc, DiscoveryLimitError):
            system_kind = "DISCOVERY_LIMIT"
        elif _contains_exception(exc, TimeoutError):
            system_kind = "DISCOVERY_TIMEOUT"
        else:
            transport_fault = (
                _contains_exception(exc, anyio.BrokenResourceError)
                or _contains_exception(exc, anyio.ClosedResourceError)
                or _contains_exception(exc, anyio.EndOfStream)
                or any(
                    marker in text.lower()
                    for marker in ("connection closed", "end of stream", "broken resource")
                )
            )
            protocol_fault = _contains_exception(exc, MCPError) or (
                _contains_runtime_message(exc, "duplicate tool name")
                or _contains_runtime_message(exc, "repeated tools/list cursor")
            )
            system_kind = (
                "TRANSPORT_ERROR"
                if transport_fault
                else "PROTOCOL_ERROR"
                if protocol_fault
                else "TRANSPORT_ERROR"
            )
        report.system_error = {
            "kind": system_kind,
            "detail": text,
        }
    report.stderr = errlog.getvalue()
    return report
