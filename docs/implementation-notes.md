# Implementation notes

## Measured environment

The committed reports were generated on Python 3.12.9 with `mcp==2.1.1` and `jsonschema==4.26.0`. The integration uses the public `StdioServerParameters`, `stdio_client`, `ClientSession`, low-level `Server`, and `stdio_server` APIs.

On this version, a 50 ms deadline around a 250 ms fixture call raises `MCPError` with `Request 'tools/call' timed out`. The next call succeeds on the same initialized session; the report records one connection and zero restarts. Invalid structured content is rejected by the SDK as `RuntimeError` beginning `Invalid structured content returned by tool`. A tool-origin failure instead returns a normal `CallToolResult` with `isError=true`. These are characterization facts for the pinned version, not promises about all SDK releases.

The stdio launcher requires stderr to expose `fileno()`. The client therefore uses an OS-managed temporary file and reads at most the configured byte limit plus one byte before redacting. A truncation marker is recorded. This bounds memory/report ingestion, but the temporary file's on-disk growth is not an application sandbox or disk quota. Context-manager completion in the integration suite is the subprocess cleanup check; the demo can rerun immediately without lingering port or process state because it uses stdio and no shared listener.

Inspection of `mcp==2.1.1` shows that `ClientSession.list_tools()` caches discovered output schemas and `call_tool()` later compiles them with `jsonschema.validators.validator_for`. The lab recursively rejects non-local `$ref`, `$dynamicRef`, and `$recursiveRef` values before calling the SDK. A real local-fragment fixture passes, while a real remote-reference fixture is rejected without executing; its server-side counter remains zero.

## Limits

- JSON Schema checks declarations and values, not business semantics.
- The configured subprocess is not sandboxed.
- Redaction recognizes common patterns and caller-supplied exact values; encoded or unusual secrets can escape detection.
- Output is bounded after redaction. A truncated value becomes an explicit preview object.
- Initialization and whole-discovery deadlines are 5 seconds by default; discovery defaults to 20 pages and 500 tools. Configured values have hard ceilings.
- Rename detection requires a unique identical contract excluding only the name. Rename plus schema change appears as removal plus addition.
- Calls run sequentially and test cases are finite, so results do not establish load behavior or production safety.

## Interview points

- Why discovery and authorization are separate trust decisions.
- Why `isError=true`, JSON-RPC errors, transport loss, timeout, and output-schema rejection need separate receipts.
- Why a timeout recovery check must use the same session to provide useful evidence.
- Why deterministic artifacts omit timestamps and durations.
- Why a read-only hint cannot authorize an operation.
