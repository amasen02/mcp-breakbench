from __future__ import annotations

import json
import sys
from pathlib import Path

from .client import discover_tools, open_session
from .models import CaseSpec, Limits, Outcome, RunSpec, ServerSpec
from .redaction import BoundedTextCapture, Redactor
from .report import write_reports
from .runner import run_bench
from .snapshot import make_snapshot

SYNTHETIC_SECRET = "demo-token-EXAMPLE-123456"


def fixture_server(mode: str) -> ServerSpec:
    return ServerSpec(sys.executable, ("-m", "mcp_breakbench.demo_servers.fixture", "--mode", mode))


async def collect_snapshot(server: ServerSpec) -> dict[str, object]:
    redactor = Redactor()
    async with open_session(server, BoundedTextCapture(16_384, redactor), 5.0) as session:
        return make_snapshot(await discover_tools(session, 20, 500))


async def run_demo(output_dir: Path) -> tuple[bool, list[str]]:
    output_dir.mkdir(parents=True, exist_ok=True)
    limits = Limits(default_timeout_seconds=1.0, max_cases=20, max_output_bytes=32_768)
    healthy = RunSpec(
        fixture_server("healthy"),
        frozenset({"echo", "sum"}),
        (
            CaseSpec("echo-control", "echo", {"message": "hello"}),
            CaseSpec("sum-control", "sum", {"a": 2, "b": 3}),
        ),
        limits,
    )
    healthy_report = await run_bench(healthy)
    write_reports(healthy_report, output_dir / "healthy.json", output_dir / "healthy.html")

    baseline = await collect_snapshot(fixture_server("baseline"))
    faulty = RunSpec(
        fixture_server("current"),
        frozenset(
            {"echo", "slow", "recovery_echo", "fail", "call_count", "secret_echo", "wrong_output"}
        ),
        (
            CaseSpec("invalid-input", "echo", {"message": 42}),
            CaseSpec("timeout", "slow", {"seconds": 0.25}, 0.05),
            CaseSpec("timeout-recovery", "recovery_echo", {"message": "recovered"}),
            CaseSpec("tool-error", "fail", {}),
            CaseSpec("annotation-is-not-authorization", "readonly_trap", {}),
            CaseSpec("trap-was-not-called", "call_count", {}),
            CaseSpec("redaction", "secret_echo", {"token": SYNTHETIC_SECRET}),
            CaseSpec("schema-mismatch", "wrong_output", {}),
        ),
        limits,
        (SYNTHETIC_SECRET,),
    )
    faulty_report = await run_bench(faulty, baseline)
    write_reports(faulty_report, output_dir / "faulty.json", output_dir / "faulty.html")
    (output_dir / "baseline.json").write_text(
        json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )

    problems: list[str] = []
    if healthy_report.has_failures or [c.outcome for c in healthy_report.cases] != [
        Outcome.PASS,
        Outcome.PASS,
    ]:
        problems.append("healthy control was not clean")
    observed = {c.outcome for c in faulty_report.cases}
    required = {
        Outcome.INPUT_VALIDATION_FAILED,
        Outcome.CALL_TIMEOUT,
        Outcome.PASS,
        Outcome.TOOL_RESULT_ERROR,
        Outcome.SAFE_SKIP_NOT_ALLOWLISTED,
        Outcome.SDK_OUTPUT_SCHEMA_REJECTED,
    }
    missing = required - observed
    if missing:
        problems.append("missing outcomes: " + ", ".join(sorted(missing)))
    drift = {d.kind for d in faulty_report.drift}
    for required_drift in {"TOOL_RENAMED", "TOOL_REMOVED", "TOOL_CHANGED"} - drift:
        problems.append(f"missing drift: {required_drift}")
    serialized = (output_dir / "faulty.json").read_text(encoding="utf-8") + (
        output_dir / "faulty.html"
    ).read_text(encoding="utf-8")
    if SYNTHETIC_SECRET in serialized:
        problems.append("synthetic secret leaked")
    return not problems, problems
