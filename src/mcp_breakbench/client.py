from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TextIO, cast

import anyio
import mcp.types as types
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from .models import ServerSpec, ToolContract
from .redaction import BoundedTextCapture


class InitializationTimeoutError(TimeoutError):
    pass


class DiscoveryLimitError(RuntimeError):
    pass


@asynccontextmanager
async def open_session(
    server: ServerSpec, errlog: BoundedTextCapture, initialization_timeout_seconds: float
) -> AsyncIterator[ClientSession]:
    params = StdioServerParameters(
        command=server.command,
        args=list(server.args),
        cwd=server.cwd,
        env=server.env,
    )
    with tempfile.TemporaryFile(mode="w+b") as child_stderr:
        try:
            async with (
                stdio_client(params, errlog=cast(TextIO, child_stderr)) as (read, write),
                ClientSession(read, write) as session,
            ):
                try:
                    with anyio.fail_after(initialization_timeout_seconds):
                        await session.initialize()
                except TimeoutError as exc:
                    raise InitializationTimeoutError("MCP initialization timed out") from exc
                yield session
        finally:
            child_stderr.seek(0)
            raw = child_stderr.read(errlog.max_bytes + 1)
            errlog.write_bytes(raw, truncated=len(raw) > errlog.max_bytes)


def _dump(value: Any) -> dict[str, Any] | None:
    return (
        value.model_dump(mode="json", by_alias=True, exclude_none=True)
        if value is not None
        else None
    )


async def discover_tools(
    session: ClientSession, max_pages: int, max_tools: int
) -> dict[str, ToolContract]:
    result = await session.list_tools()
    pages = 1
    seen_cursors: set[str] = set()
    found: dict[str, ToolContract] = {}
    while True:
        for tool in result.tools:
            if tool.name in found:
                raise RuntimeError(f"duplicate tool name: {tool.name}")
            if len(found) >= max_tools:
                raise DiscoveryLimitError(f"tools/list exceeded max_tools={max_tools}")
            found[tool.name] = ToolContract(
                name=tool.name,
                title=tool.title,
                description=tool.description,
                input_schema=tool.input_schema,
                output_schema=tool.output_schema,
                annotations=_dump(tool.annotations),
            )
        cursor = result.next_cursor
        if not cursor:
            return found
        if cursor in seen_cursors:
            raise RuntimeError("repeated tools/list cursor")
        if pages >= max_pages:
            raise DiscoveryLimitError(f"tools/list exceeded max_tool_pages={max_pages}")
        seen_cursors.add(cursor)
        pages += 1
        result = await session.list_tools(params=types.PaginatedRequestParams(cursor=cursor))
