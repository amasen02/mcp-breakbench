from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from mcp_breakbench.config import ConfigError, load_run_spec
from mcp_breakbench.models import BenchReport, CaseReceipt, Outcome, ToolContract
from mcp_breakbench.redaction import BoundedTextCapture, Redactor, bound_value
from mcp_breakbench.report import render_html, render_json
from mcp_breakbench.schemas import UnsafeSchemaReference, validate_instance, validate_schema
from mcp_breakbench.snapshot import diff_snapshots, make_snapshot


def test_config_rejects_case_bound_before_spawn(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {
                "server": {"command": "never-run", "args": []},
                "allow_tools": [],
                "limits": {"max_cases": 1},
                "cases": [
                    {"id": "a", "tool": "x", "arguments": {}},
                    {"id": "b", "tool": "x", "arguments": {}},
                ],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="max_cases"):
        load_run_spec(path)


def test_config_resolves_relative_cwd(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"server": {"command": "x", "args": [], "cwd": "work"}, "allow_tools": [], "cases": []}
        ),
        encoding="utf-8",
    )
    assert load_run_spec(path).server.cwd == str((tmp_path / "work").resolve())


def test_bad_numeric_limit_is_config_error_and_cli_exit_two(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = json.dumps(
        {
            "server": {"command": "must-not-run", "args": []},
            "allow_tools": [],
            "cases": [],
            "limits": {"max_cases": "many"},
        }
    )
    path.write_text(original, encoding="utf-8")
    with pytest.raises(ConfigError, match="must be an integer"):
        load_run_spec(path)
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_breakbench",
            "run",
            str(path),
            "--json-out",
            str(tmp_path / "out.json"),
            "--html-out",
            str(tmp_path / "out.html"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "configuration/output error" in completed.stderr


def test_cli_rejects_output_input_collision_before_server_call(tmp_path: Path) -> None:
    path = tmp_path / "config.json"
    original = json.dumps(
        {"server": {"command": "must-not-run", "args": []}, "allow_tools": [], "cases": []}
    )
    path.write_text(original, encoding="utf-8")
    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "mcp_breakbench",
            "run",
            str(path),
            "--json-out",
            str(path),
            "--html-out",
            str(tmp_path / "out.html"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 2
    assert "path collision" in completed.stderr
    assert path.read_text(encoding="utf-8") == original
    assert not (tmp_path / "out.html").exists()


def test_schema_validation_and_invalid_schema() -> None:
    schema = {"type": "object", "properties": {"n": {"type": "integer"}}, "required": ["n"]}
    assert validate_instance(schema, {"n": "x"}) == ["n: 'x' is not of type 'integer'"]
    assert validate_schema({"type": "definitely-not-a-type"}) is not None


def test_local_schema_ref_works_and_remote_ref_is_rejected_without_resolution() -> None:
    local = {
        "$defs": {"number": {"type": "integer"}},
        "$ref": "#/$defs/number",
    }
    assert validate_schema(local) is None
    assert validate_instance(local, 3) == []
    remote = {"type": "object", "properties": {"x": {"$ref": "https://example.invalid/x"}}}
    assert "non-local JSON Schema reference" in str(validate_schema(remote))
    with pytest.raises(UnsafeSchemaReference):
        validate_instance(remote, {"x": 1})


def test_redaction_is_recursive_but_preserves_schema_property_definition() -> None:
    value = {
        "token": "demo-token-123456",
        "nested": {"authorization": "Bearer abcdefghij"},
        "properties": {"token": {"type": "string"}},
    }
    clean = Redactor(("demo-token-123456",)).value(value)
    assert clean["token"] == "[REDACTED]"
    assert clean["nested"]["authorization"] == "[REDACTED]"
    assert clean["properties"]["token"] == {"type": "string"}


def test_bound_value_marks_truncation_and_keeps_valid_unicode() -> None:
    bounded = bound_value({"text": "😀" * 100}, 80)
    assert bounded["truncated"] is True
    bounded["preview"].encode("utf-8")


def test_stderr_capture_accepts_only_bounded_bytes() -> None:
    capture = BoundedTextCapture(32, Redactor())
    capture.write_bytes(b"x" * 100, truncated=True)
    assert len(capture.getvalue().encode("utf-8")) <= 32
    assert capture.getvalue().endswith("...[STDERR TRUNCATED]")


def test_snapshot_detects_conservative_rename_remove_and_change() -> None:
    schema = {"type": "object"}

    def contract(name: str, description: str = "same", output: dict | None = None) -> ToolContract:
        return ToolContract(name, None, description, schema, output, None)

    old = make_snapshot(
        {"old": contract("old"), "gone": contract("gone", "gone"), "stable": contract("stable")}
    )
    new = make_snapshot({"new": contract("new"), "stable": contract("stable", output=schema)})
    kinds = {(x.kind, x.tool) for x in diff_snapshots(old, new)}
    assert {("TOOL_RENAMED", "old"), ("TOOL_REMOVED", "gone"), ("TOOL_CHANGED", "stable")} <= kinds


def test_html_escapes_dynamic_values_and_json_is_deterministic() -> None:
    report = BenchReport(server="<script>alert(1)</script>")
    report.cases.append(CaseReceipt("a&b", "x", Outcome.CLIENT_RUNTIME_ERROR, '"<unsafe>"'))
    rendered = render_html(report)
    assert "<script>alert" not in rendered
    assert "&lt;script&gt;" in rendered and "&lt;unsafe&gt;" in rendered and "a&amp;b" in rendered
    assert render_json(report) == render_json(report)
