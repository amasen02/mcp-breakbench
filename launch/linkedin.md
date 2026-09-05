“The MCP tool failed” is not a diagnosis.

`mcp-breakbench` runs explicit, allowlisted cases against a local stdio server and records deterministic receipts. Its measured faulty fixture separates invalid input, timeout plus same-session recovery, `isError=true`, SDK output-schema rejection, transport boundaries, redaction, annotation-safe skipping, and contract drift.

Run the model-free demo with Python 3.11+:

`python -m venv .venv` → install editable → `.venv\Scripts\python -m mcp_breakbench demo --output-dir demo/reports`

The receipt shows one connection and zero restarts after timeout recovery. Snapshot diffs identify a conservative rename, removal, and schema change. The project documents its limits: the configured process is trusted code, JSON Schema cannot prove business semantics, and redaction is defense in depth.

Built with AI assistance from a user-directed brief; tests, fixtures, reports, and limitations are inspectable. Repository: [mcp-breakbench](https://github.com/amasen02/mcp-breakbench)
