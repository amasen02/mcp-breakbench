from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any

import anyio

from .client import discover_tools, open_session
from .config import ConfigError, load_run_spec
from .demo import run_demo
from .redaction import BoundedTextCapture, Redactor
from .report import write_reports
from .runner import run_bench
from .snapshot import make_snapshot


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mcp-breakbench", description="Reproduce MCP contract failures safely"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    snapshot = sub.add_parser("snapshot", help="discover and save tool contracts")
    snapshot.add_argument("config", type=Path)
    snapshot.add_argument("--output", required=True, type=Path)
    run = sub.add_parser("run", help="run explicit allowlisted cases")
    run.add_argument("config", type=Path)
    run.add_argument("--snapshot", type=Path)
    run.add_argument("--json-out", required=True, type=Path)
    run.add_argument("--html-out", required=True, type=Path)
    demo = sub.add_parser("demo", help="run bundled healthy and faulty servers")
    demo.add_argument("--output-dir", type=Path, default=Path("demo/reports"))
    return parser


def _load_snapshot(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("tools"), list):
        raise ConfigError("snapshot must contain a tools array")
    return value


def _reject_path_collisions(**paths: Path | None) -> None:
    resolved: dict[Path, str] = {}
    for label, path in paths.items():
        if path is None:
            continue
        key = path.resolve()
        previous = resolved.get(key)
        if previous is not None:
            raise ConfigError(f"path collision: {previous} and {label} resolve to the same path")
        resolved[key] = label


async def _snapshot(config_path: Path, output: Path) -> int:
    spec = load_run_spec(config_path)
    redactor = Redactor(spec.redaction_values)
    async with open_session(
        spec.server,
        BoundedTextCapture(spec.limits.max_stderr_bytes, redactor),
        spec.limits.initialization_timeout_seconds,
    ) as session:
        try:
            with anyio.fail_after(spec.limits.discovery_timeout_seconds):
                snapshot = redactor.value(
                    make_snapshot(
                        await discover_tools(
                            session, spec.limits.max_tool_pages, spec.limits.max_tools
                        )
                    )
                )
        except TimeoutError as exc:
            raise TimeoutError("MCP tool discovery timed out") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0


async def _main_async(args: argparse.Namespace) -> int:
    if args.command == "demo":
        ok, problems = await run_demo(args.output_dir)
        if ok:
            print(f"demo reports written to {args.output_dir}")
            return 0
        print("demo failed: " + "; ".join(problems), file=sys.stderr)
        return 1
    if args.command == "snapshot":
        _reject_path_collisions(config=args.config, output=args.output)
        return await _snapshot(args.config, args.output)
    _reject_path_collisions(
        config=args.config,
        snapshot=args.snapshot,
        json_out=args.json_out,
        html_out=args.html_out,
    )
    spec = load_run_spec(args.config)
    report = await run_bench(spec, _load_snapshot(args.snapshot))
    write_reports(report, args.json_out, args.html_out)
    if report.system_error:
        return 3
    return 1 if report.has_failures else 0


def main() -> int:
    try:
        return asyncio.run(_main_async(_parser().parse_args()))
    except (ConfigError, OSError, json.JSONDecodeError) as exc:
        print(f"configuration/output error: {exc}", file=sys.stderr)
        return 2
    except BaseException as exc:
        if isinstance(exc, (KeyboardInterrupt, SystemExit)):
            raise
        print(f"transport/protocol error: {exc}", file=sys.stderr)
        return 3


if __name__ == "__main__":
    raise SystemExit(main())
