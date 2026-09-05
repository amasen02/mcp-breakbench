from __future__ import annotations

import html
import json
from pathlib import Path

from .models import BenchReport


def render_json(report: BenchReport) -> str:
    return (
        json.dumps(report.to_dict(), indent=2, sort_keys=True, ensure_ascii=False, allow_nan=False)
        + "\n"
    )


def render_html(report: BenchReport) -> str:
    data = report.to_dict()
    rows = []
    for case in data["cases"]:
        rows.append(
            "<tr><td>"
            + html.escape(str(case["id"]), quote=True)
            + "</td><td>"
            + html.escape(str(case["tool"]), quote=True)
            + "</td><td><code>"
            + html.escape(str(case["outcome"]), quote=True)
            + "</code></td><td>"
            + html.escape(str(case["detail"]), quote=True)
            + "</td></tr>"
        )
    drift = (
        "".join(
            f"<li><code>{html.escape(str(item['kind']), quote=True)}</code> "
            f"{html.escape(str(item['tool']), quote=True)}</li>"
            for item in data["drift"]
        )
        or "<li>None</li>"
    )
    error = (
        html.escape(json.dumps(data["system_error"], sort_keys=True), quote=True)
        if data["system_error"]
        else "None"
    )
    document = (
        """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>mcp-breakbench report</title><style>
body{font:16px system-ui;max-width:70rem;margin:2rem auto;padding:0 1rem;color:#17202a}
table{border-collapse:collapse;width:100%}
th,td{border:1px solid #ccd;padding:.55rem;text-align:left}
code{background:#eef3f7;padding:.1rem .25rem}
pre{white-space:pre-wrap;background:#f5f6f7;padding:1rem}
</style></head><body><h1>mcp-breakbench report</h1>
<p>Server command: <code>"""
        + html.escape(str(data["server"]), quote=True)
        + """</code></p>
<p>This report is interoperability evidence, not a security certification.</p>
<h2>Contract drift</h2><ul>"""
        + drift
        + """</ul>
<h2>Cases</h2><table><thead><tr><th>ID</th><th>Tool</th><th>Outcome</th><th>Detail</th></tr></thead>
<tbody>"""
        + "".join(rows)
        + """</tbody></table>
<h2>System error</h2><pre>"""
        + error
        + """</pre></body></html>
"""
    )
    return str(document)


def write_reports(report: BenchReport, json_path: Path, html_path: Path) -> None:
    json_path.parent.mkdir(parents=True, exist_ok=True)
    html_path.parent.mkdir(parents=True, exist_ok=True)
    json_path.write_text(render_json(report), encoding="utf-8")
    html_path.write_text(render_html(report), encoding="utf-8")
