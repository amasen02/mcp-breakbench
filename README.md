# mcp-breakbench

Reproduce an MCP tool failure before blaming the agent. `mcp-breakbench` launches a configured server over stdio with the official Python SDK, snapshots its advertised tool contracts, and runs only explicit cases approved by a local allowlist. It produces deterministic JSON receipts and an escaped static HTML report.

This is an interoperability and regression lab. It is not a process sandbox, vulnerability scanner, or security certification.

## One-command demo

Python 3.11 or newer is required. The demo is model-free and uses only local synthetic servers.

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m mcp_breakbench demo --output-dir demo/reports
# POSIX
.venv/bin/python -m pip install -e .
.venv/bin/python -m mcp_breakbench demo --output-dir demo/reports
```

The command starts real MCP subprocesses and writes `healthy.json/html`, `faulty.json/html`, and the baseline snapshot. The faulty report demonstrates invalid fixture input, a timeout with same-session recovery, a tool-origin error, output-schema rejection, redaction, annotation-safe skipping, and tool drift.

## Use your server

```bash
mcp-breakbench snapshot demo/configs/healthy.json --output baseline.json
mcp-breakbench run demo/configs/healthy.json --snapshot baseline.json --json-out report.json --html-out report.html
```

Configuration contains a command plus an argument array, an explicit `allow_tools` list, and explicit cases. Discovered descriptions and annotations never create or authorize calls. The configured command is trusted operator input and runs with the current user's permissions.

See [the demo guide](docs/demo.md), [architecture](docs/architecture.md), and [implementation notes](docs/implementation-notes.md).

## Limitations

The lab checks declared JSON Schemas and observable MCP behavior on finite fixtures. It cannot prove semantic correctness, safety, idempotency, or production readiness. Redaction is defense in depth and cannot recognize every possible secret format. Rename detection is deliberately conservative.

Initialization, total discovery time, tool pages, discovered tool count, cases, call time, stderr, and result output are all bounded. Non-local `$ref`, `$dynamicRef`, and `$recursiveRef` values are rejected before a tool call; local fragment references remain supported.

This repository was built with AI assistance and verified through deterministic local tests. A useful owner exercise is to add a synthetic tool to the fixture server, save the old snapshot, change its schema, and explain the resulting JSON receipt without reading the implementation.
