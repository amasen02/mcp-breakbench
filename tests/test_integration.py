from __future__ import annotations

import asyncio
import json
import subprocess
import sys
from pathlib import Path

from mcp_breakbench.demo import SYNTHETIC_SECRET, fixture_server, run_demo
from mcp_breakbench.models import CaseSpec, Limits, Outcome, RunSpec, ServerSpec
from mcp_breakbench.runner import run_bench


def test_real_stdio_demo_covers_required_failures(tmp_path: Path) -> None:
    ok, problems = asyncio.run(run_demo(tmp_path))
    assert ok, problems
    healthy = json.loads((tmp_path / "healthy.json").read_text(encoding="utf-8"))
    faulty = json.loads((tmp_path / "faulty.json").read_text(encoding="utf-8"))
    assert [case["outcome"] for case in healthy["cases"]] == ["PASS", "PASS"]
    cases = {case["id"]: case for case in faulty["cases"]}
    assert cases["invalid-input"]["outcome"] == "INPUT_VALIDATION_FAILED"
    assert cases["timeout"]["outcome"] == "CALL_TIMEOUT"
    assert cases["timeout-recovery"]["outcome"] == "PASS"
    assert cases["tool-error"]["outcome"] == "TOOL_RESULT_ERROR"
    assert cases["annotation-is-not-authorization"]["outcome"] == "SAFE_SKIP_NOT_ALLOWLISTED"
    assert cases["trap-was-not-called"]["structured_content"] == {"count": 0}
    assert cases["schema-mismatch"]["outcome"] == "SDK_OUTPUT_SCHEMA_REJECTED"
    assert faulty["connections_opened"] == 1 and faulty["session_restarts"] == 0
    kinds = {item["kind"] for item in faulty["drift"]}
    assert {"TOOL_RENAMED", "TOOL_REMOVED", "TOOL_CHANGED"} <= kinds
    combined = (tmp_path / "faulty.json").read_text(encoding="utf-8") + (
        tmp_path / "faulty.html"
    ).read_text(encoding="utf-8")
    assert SYNTHETIC_SECRET not in combined
    assert "fixture stderr Bearer [REDACTED]" in faulty["stderr"]


def test_transport_exit_is_not_tool_error() -> None:
    spec = RunSpec(
        ServerSpec(sys.executable, ("-m", "mcp_breakbench.demo_servers.exit_early")),
        frozenset(),
        (),
        Limits(),
    )
    report = asyncio.run(run_bench(spec))
    assert report.system_error is not None
    assert report.system_error["kind"] == "TRANSPORT_ERROR"
    assert not report.cases


def test_public_cli_writes_real_demo(tmp_path: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "mcp_breakbench", "demo", "--output-dir", str(tmp_path)],
        text=True,
        capture_output=True,
        check=False,
        timeout=20,
    )
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "healthy.html").is_file() and (tmp_path / "faulty.json").is_file()


def test_discovery_only_never_calls_tools() -> None:
    spec = RunSpec(fixture_server("healthy"), frozenset({"readonly_trap"}), (), Limits())
    report = asyncio.run(run_bench(spec))
    assert report.system_error is None and report.cases == []
    assert any(tool["name"] == "readonly_trap" for tool in report.tools)


def test_allowlisted_missing_tool_is_safe_skip() -> None:
    spec = RunSpec(
        fixture_server("healthy"),
        frozenset({"does_not_exist"}),
        (CaseSpec("missing", "does_not_exist", {}),),
        Limits(),
    )
    report = asyncio.run(run_bench(spec))
    assert report.cases[0].outcome == Outcome.SAFE_SKIP_TOOL_MISSING


def test_initialization_and_discovery_have_deadlines() -> None:
    startup = RunSpec(
        fixture_server("hang-initialize"),
        frozenset(),
        (),
        Limits(initialization_timeout_seconds=0.05),
    )
    startup_report = asyncio.run(run_bench(startup))
    assert startup_report.system_error is not None
    assert startup_report.system_error["kind"] == "INITIALIZATION_TIMEOUT"

    discovery = RunSpec(
        fixture_server("hang-list"),
        frozenset(),
        (),
        Limits(discovery_timeout_seconds=0.05),
    )
    discovery_report = asyncio.run(run_bench(discovery))
    assert discovery_report.system_error is not None
    assert discovery_report.system_error["kind"] == "DISCOVERY_TIMEOUT"


def test_unique_pagination_is_bounded() -> None:
    spec = RunSpec(
        fixture_server("paginate"),
        frozenset(),
        (),
        Limits(max_tool_pages=3, max_tools=10),
    )
    report = asyncio.run(run_bench(spec))
    assert report.system_error is not None
    assert report.system_error["kind"] == "DISCOVERY_LIMIT"
    assert "max_tool_pages=3" in report.system_error["detail"]


def test_remote_ref_is_rejected_before_sdk_call_but_local_ref_runs() -> None:
    spec = RunSpec(
        fixture_server("healthy"),
        frozenset({"remote_ref", "local_ref", "call_count"}),
        (
            CaseSpec("remote", "remote_ref", {}),
            CaseSpec("local", "local_ref", {"message": "ok"}),
            CaseSpec("count", "call_count", {}),
        ),
        Limits(),
    )
    report = asyncio.run(run_bench(spec))
    cases = {case.id: case for case in report.cases}
    assert cases["remote"].outcome == Outcome.OUTPUT_SCHEMA_INVALID
    assert cases["local"].outcome == Outcome.PASS
    assert cases["count"].structured_content == {"count": 0}
