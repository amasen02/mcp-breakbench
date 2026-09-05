# Reproduce an MCP tool failure before blaming the agent

When an agent reports that a tool failed, the report often collapses several different events into one vague error. Invalid input, a server-declared tool error, a timeout, a transport exit, and an output-schema rejection have different causes and different recovery choices. Treating them as the same failure makes debugging slower and can authorize the wrong retry.

`mcp-breakbench` is a local interoperability and regression lab for making those distinctions observable. It launches a configured MCP server over stdio with the official Python SDK, snapshots the advertised tool contracts, runs only explicit cases approved by an allowlist, and writes deterministic JSON receipts plus an escaped static HTML report. Its demo uses synthetic servers, so the result is repeatable without a model or network service.

## Run the fixture

Python 3.11 or newer is required:

```bash
python -m venv .venv
# Windows
.venv\Scripts\python -m pip install -e .
.venv\Scripts\python -m mcp_breakbench demo --output-dir demo/reports
# POSIX
.venv/bin/python -m pip install -e .
.venv/bin/python -m mcp_breakbench demo --output-dir demo/reports
```

The demo starts real local MCP subprocesses and writes `healthy.json`, `faulty.json`, and a baseline snapshot. The healthy report has two passing control calls. The faulty report is expected to contain failures; the demo succeeds only when it observes the predefined failure classes and tool drift.

The measured faulty receipt contains an `invalid-input` case with `INPUT_VALIDATION_FAILED`, followed by a 250 ms fixture call that times out as `CALL_TIMEOUT`. The next case passes on the same session as `timeout-recovery`; the receipt records one connection and zero session restarts. A server result with `isError=true` is recorded as `TOOL_RESULT_ERROR`. Invalid structured output is recorded separately as `SDK_OUTPUT_SCHEMA_REJECTED`.

The case named `annotation-is-not-authorization` is safely skipped because the tool is not in the explicit allowlist, even though it advertises `readOnlyHint=true`. The following `trap-was-not-called` receipt shows a count of zero. Secret-shaped values are redacted in arguments, content, structured content, and stderr. The snapshot diff identifies a conservative rename, a removal, and a changed input/output schema.

## The trust boundary

The configuration contains a server command and argument array, an `allow_tools` set, finite cases, and limits. The configured command is trusted operator input and runs with the current user’s permissions; this project is not a process sandbox, vulnerability scanner, or security certification.

Discovery and authorization are separate decisions. The runner can discover a tool without calling it. Tool descriptions and annotations never create cases or grant permission. A call must have both a named case and allowlist membership, and its arguments must satisfy the discovered input schema before the SDK call begins.

The runner keeps one MCP session for sequential cases. A timeout becomes a receipt, and the next case can test recovery without hiding whether a restart occurred. Transport loss is reported as a system error rather than being mislabelled as a tool-origin failure. These distinctions make a receipt useful for deciding whether to fix arguments, inspect server code, retry in the same session, or investigate process health.

## Contract and output checks

Before calls, the lab validates discovered JSON Schemas. Local fragment references work. Non-local `$ref`, `$dynamicRef`, and `$recursiveRef` values are rejected before `ClientSession.call_tool`, so the SDK cannot fetch a discovered remote reference while validating output. The real fixture proves the boundary: the remote-reference case is rejected, the local-reference case passes, and a counter remains zero where no unauthorized call should occur.

The demo uses the SDK’s `CallToolResult` behavior as characterized for the pinned `mcp==2.1.1`. A tool-origin error is a normal result with `isError=true`. Bad structured content raises the SDK’s output validator path. These are measured facts for the pinned dependency, not promises that every future SDK version will raise the same exception text.

Receipts are deterministic: timestamps and durations are omitted. Text capture is byte-bounded and redacted before it enters the report. A truncation marker makes loss visible. HTML escapes dynamic values. Temporary stderr storage bounds application reads, but it is not a disk quota or a sandbox.

## Tradeoffs and exercise

The lab favors finite, inspectable cases over load testing. JSON Schema checks declarations and values, not business semantics, idempotency, or safety. Redaction handles common patterns and caller-supplied exact values; encoded or unusual secrets may escape detection. Rename detection requires one unique identical contract apart from the name, so a rename plus schema change appears as removal plus addition. Initialization and complete discovery have separate deadlines, with hard page and tool-count ceilings.

For an owner exercise, add a synthetic tool to the fixture server, save the old snapshot, change its schema, and explain the resulting receipt without reading the implementation. Then add a case that proves a read-only annotation does not authorize a call. Inspect `faulty.json` and `faulty.html` before consulting `docs/interview.md`, which ties the exercise to the concrete runner and fixture code.

The repository was built with AI assistance from a user-directed brief. Tests, deterministic reports, and limitations are included so the behavior can be checked directly. Local verification recorded 20 passing tests with the pinned Python 3.12.9 environment; no production server, adoption, or security certification is claimed.

Repository: [mcp-breakbench](https://github.com/amasen02/mcp-breakbench).
