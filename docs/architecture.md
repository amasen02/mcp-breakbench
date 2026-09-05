# Architecture

```mermaid
flowchart LR
  C[Local JSON config] --> V[Bounded config validation]
  V --> P[Official SDK stdio process]
  P --> D[Tool discovery and snapshot]
  D --> S[Local JSON Schema gates]
  A[Explicit cases plus allowlist] --> S
  S -->|authorized and valid| T[Sequential tool calls]
  S -->|denied or invalid| R[Typed receipts]
  T --> R
  D --> F[Contract drift]
  F --> R
  R --> X[Redaction and byte bounds]
  X --> J[Deterministic JSON]
  X --> H[Escaped static HTML]
```

The execution boundary is the pair of local controls: a named case and allowlist membership. Schema discovery does not generate cases, and annotations do not grant permission. Commands and argument arrays pass directly to `StdioServerParameters`; server text never enters a shell.

The runner keeps one MCP session for deterministic sequential calls. A request timeout is recorded and the next case uses the same session, making recovery observable. Snapshot comparison identifies exact contract changes and only labels a rename when one removed and one added tool have identical contracts apart from name.

Initialization and the complete discovery loop have separate deadlines. Discovery also has hard page and tool-count limits, including protection against an endless stream of unique cursors. Schema inspection recursively rejects non-local references before any case reaches `ClientSession.call_tool`, preventing the SDK's cached output validator from fetching a discovered remote reference.
