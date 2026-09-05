# Security policy

`mcp-breakbench` is an interoperability test tool, not a sandbox or security certification. A configured server command is trusted operator input and runs with the invoking user's permissions. Review config files before running them.

Tool annotations, including `readOnlyHint`, are treated as metadata and never as authorization. Calls require an explicit case and explicit allowlist membership. Avoid fixtures that touch real accounts or production data.

Reports redact common credential shapes and configured exact values. This cannot cover every encoding or domain-specific secret. Child stderr is captured in an OS-managed temporary file for the lifetime of a connection because the official stdio launcher requires a file descriptor. The read into memory is bounded, then redacted before entering a report, and the file is closed. Its on-disk growth is governed by the operating system rather than this tool; run untrusted servers inside a separately configured OS/container sandbox with disk quotas.

Discovered JSON Schemas may be hostile. Non-local references are rejected recursively before custom or SDK result validation can resolve them. Local fragment references beginning with `#` are supported.

If this repository is hosted, report vulnerabilities through the host's private security-advisory feature. Do not include live credentials in a report.
