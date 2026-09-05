from __future__ import annotations

import hashlib
import json
from typing import Any

from .models import DriftFinding, ToolContract


def make_snapshot(tools: dict[str, ToolContract]) -> dict[str, Any]:
    return {"schema_version": "1", "tools": [tools[name].to_dict() for name in sorted(tools)]}


def _fingerprint(tool: dict[str, Any], include_name: bool = True) -> str:
    value = dict(tool)
    if not include_name:
        value.pop("name", None)
    raw = json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    )
    return hashlib.sha256(raw.encode()).hexdigest()


def diff_snapshots(baseline: dict[str, Any], current: dict[str, Any]) -> list[DriftFinding]:
    old = {x["name"]: x for x in baseline.get("tools", [])}
    new = {x["name"]: x for x in current.get("tools", [])}
    findings: list[DriftFinding] = []
    for name in sorted(old.keys() & new.keys()):
        if _fingerprint(old[name]) != _fingerprint(new[name]):
            fields = sorted(
                k
                for k in old[name].keys() | new[name].keys()
                if old[name].get(k) != new[name].get(k)
            )
            findings.append(DriftFinding("TOOL_CHANGED", name, {"fields": fields}))
    removed, added = set(old) - set(new), set(new) - set(old)
    matched_old: set[str] = set()
    matched_new: set[str] = set()
    for old_name in sorted(removed):
        candidates = [
            n for n in added if _fingerprint(old[old_name], False) == _fingerprint(new[n], False)
        ]
        if len(candidates) == 1:
            new_name = candidates[0]
            reverse = [
                o
                for o in removed
                if _fingerprint(old[o], False) == _fingerprint(new[new_name], False)
            ]
            if len(reverse) == 1:
                findings.append(DriftFinding("TOOL_RENAMED", old_name, {"new_name": new_name}))
                matched_old.add(old_name)
                matched_new.add(new_name)
    findings.extend(DriftFinding("TOOL_REMOVED", n) for n in sorted(removed - matched_old))
    findings.extend(DriftFinding("TOOL_ADDED", n) for n in sorted(added - matched_new))
    return sorted(findings, key=lambda x: (x.kind, x.tool))
