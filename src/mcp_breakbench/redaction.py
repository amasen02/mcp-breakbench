from __future__ import annotations

import json
import re
from typing import Any

MASK = "[REDACTED]"
SENSITIVE_KEY = re.compile(r"(?:authorization|api[_-]?key|token|password|secret)", re.I)
PATTERNS = [
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"),
    re.compile(r"(?i)(?:sk|api)[_-][A-Za-z0-9_-]{8,}"),
    re.compile(r"(?i)https?://[^\s/@:]+:[^\s/@]+@"),
    re.compile(r"-----BEGIN [^-]+-----[\s\S]*?-----END [^-]+-----"),
]


class Redactor:
    def __init__(self, extra_values: tuple[str, ...] = ()) -> None:
        self.extra_values = tuple(sorted((x for x in extra_values if x), key=len, reverse=True))

    def text(self, value: str) -> str:
        result = value
        for secret in self.extra_values:
            result = result.replace(secret, MASK)
        for pattern in PATTERNS:
            result = pattern.sub(MASK, result)
        return result

    def value(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(k): MASK
                if SENSITIVE_KEY.search(str(k)) and not isinstance(v, (dict, list, tuple))
                else self.value(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [self.value(x) for x in value]
        if isinstance(value, tuple):
            return [self.value(x) for x in value]
        return self.text(value) if isinstance(value, str) else value


def bound_value(value: Any, max_bytes: int) -> Any:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    if len(encoded) <= max_bytes:
        return value
    marker = f"...[TRUNCATED; original_bytes={len(encoded)}]"
    room = max(0, max_bytes - len(marker.encode("utf-8")))
    preview = encoded[:room].decode("utf-8", errors="ignore") + marker
    return {"truncated": True, "preview": preview}


class BoundedTextCapture:
    def __init__(self, max_bytes: int, redactor: Redactor) -> None:
        self.max_bytes = max_bytes
        self.redactor = redactor
        self._text = ""

    def write(self, data: str) -> int:
        clean = self.redactor.text(data)
        combined = (self._text + clean).encode("utf-8")[: self.max_bytes]
        self._text = combined.decode("utf-8", errors="ignore")
        return len(data)

    def flush(self) -> None:
        return None

    def getvalue(self) -> str:
        return self._text

    def write_bytes(self, data: bytes, truncated: bool = False) -> None:
        decoded = data.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
        clean = self.redactor.text(decoded)
        marker = "...[STDERR TRUNCATED]" if truncated else ""
        marker_bytes = marker.encode("utf-8")
        room = max(0, self.max_bytes - len(marker_bytes))
        bounded = clean.encode("utf-8")[:room].decode("utf-8", errors="ignore")
        self._text = bounded + marker
