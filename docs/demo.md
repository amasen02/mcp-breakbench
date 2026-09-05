# Demo guide

From an activated project virtual environment:

```bash
mcp-breakbench demo --output-dir demo/reports
```

Expected terminal output is `demo reports written to demo/reports` with exit code 0. The healthy report has two passing calls. The faulty report is expected to contain failures; the demo command succeeds only when it observes the predefined failure classes and drift.

Open `demo/reports/faulty.html` locally. Check these receipts:

1. `invalid-input` fails before an MCP call.
2. `timeout` is followed by a passing `timeout-recovery`, with one connection and zero restarts.
3. `tool-error` is `TOOL_RESULT_ERROR`, while invalid structured output is `SDK_OUTPUT_SCHEMA_REJECTED`.
4. `annotation-is-not-authorization` is skipped even though the server advertises `readOnlyHint=true`; `trap-was-not-called` returns zero.
5. Secret-shaped data is replaced with `[REDACTED]` in arguments, content, structured content, and captured stderr.
6. Drift includes a conservative rename, removal, and changed input/output schema.

The files are synthetic and deterministic. Rerunning the command should leave them byte-for-byte unchanged.

