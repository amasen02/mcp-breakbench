from __future__ import annotations

import argparse
import asyncio
import sys
from typing import Any

import anyio
import mcp.types as types
from mcp.server.lowlevel import NotificationOptions, Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server

OBJECT = {"type": "object", "additionalProperties": False}
STRING_RESULT = {**OBJECT, "properties": {"message": {"type": "string"}}, "required": ["message"]}
EMPTY = {**OBJECT, "properties": {}}
counter = 0


def tool(
    name: str,
    input_schema: dict[str, Any],
    output_schema: dict[str, Any] | None = None,
    *,
    read_only: bool = False,
    description: str | None = None,
) -> types.Tool:
    annotations = types.ToolAnnotations(read_only_hint=True) if read_only else None
    return types.Tool(
        name=name,
        description=description or f"Synthetic {name} fixture",
        input_schema=input_schema,
        output_schema=output_schema,
        annotations=annotations,
    )


def schemas(mode: str) -> list[types.Tool]:
    text_input = {**OBJECT, "properties": {"message": {"type": "string"}}, "required": ["message"]}
    tools = [tool("echo", text_input, STRING_RESULT)]
    if mode == "baseline":
        return tools + [
            tool(
                "legacy_echo",
                text_input,
                STRING_RESULT,
                description="Synthetic renamed contract fixture",
            ),
            tool("will_remove", EMPTY, EMPTY),
            tool("changing", text_input, STRING_RESULT),
        ]
    common = [
        tool(
            "sum",
            {
                **OBJECT,
                "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
                "required": ["a", "b"],
            },
            {**OBJECT, "properties": {"sum": {"type": "integer"}}, "required": ["sum"]},
        ),
        tool("fail", EMPTY),
        tool(
            "slow",
            {**OBJECT, "properties": {"seconds": {"type": "number"}}, "required": ["seconds"]},
        ),
        tool("recovery_echo", text_input, STRING_RESULT),
        tool(
            "readonly_trap",
            EMPTY,
            {**OBJECT, "properties": {"count": {"type": "integer"}}, "required": ["count"]},
            read_only=True,
        ),
        tool(
            "call_count",
            EMPTY,
            {**OBJECT, "properties": {"count": {"type": "integer"}}, "required": ["count"]},
        ),
        tool(
            "secret_echo",
            {**OBJECT, "properties": {"token": {"type": "string"}}, "required": ["token"]},
            {
                **OBJECT,
                "properties": {"token": {"type": "string"}, "nested": {"type": "object"}},
                "required": ["token", "nested"],
            },
        ),
        tool("html_echo", text_input, STRING_RESULT),
        tool(
            "local_ref",
            {
                **OBJECT,
                "$defs": {"text": {"type": "string"}},
                "properties": {"message": {"$ref": "#/$defs/text"}},
                "required": ["message"],
            },
            STRING_RESULT,
        ),
        tool(
            "remote_ref",
            EMPTY,
            {
                **OBJECT,
                "properties": {"message": {"$ref": "https://example.invalid/schema.json"}},
                "required": ["message"],
            },
        ),
    ]
    if mode == "current":
        common += [
            tool(
                "renamed_echo",
                text_input,
                STRING_RESULT,
                description="Synthetic renamed contract fixture",
            ),
            tool(
                "changing",
                {**OBJECT, "properties": {"message": {"type": "integer"}}, "required": ["message"]},
                {**OBJECT, "properties": {"message": {"type": "integer"}}, "required": ["message"]},
            ),
            tool(
                "wrong_output",
                EMPTY,
                {**OBJECT, "properties": {"count": {"type": "integer"}}, "required": ["count"]},
            ),
        ]
    return tools + common


async def list_tools(_ctx: Any, _params: Any) -> types.ListToolsResult:
    if MODE == "hang-list":
        await anyio.sleep(10)
    if MODE == "paginate":
        page = int(_params.cursor) if _params and _params.cursor else 0
        return types.ListToolsResult(
            tools=[tool(f"page_{page}", EMPTY, EMPTY)], next_cursor=str(page + 1)
        )
    return types.ListToolsResult(tools=schemas(MODE))


async def call_tool(_ctx: Any, params: types.CallToolRequestParams) -> types.CallToolResult:
    global counter
    name, args = params.name, params.arguments or {}
    if name in {
        "echo",
        "legacy_echo",
        "renamed_echo",
        "recovery_echo",
        "html_echo",
        "local_ref",
    }:
        if name == "echo":
            counter += 1
        value = args["message"]
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=value)],
            structured_content={"message": value},
        )
    if name == "sum":
        value = args["a"] + args["b"]
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(value))],
            structured_content={"sum": value},
        )
    if name == "fail":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="synthetic tool failure")], is_error=True
        )
    if name == "slow":
        await anyio.sleep(float(args["seconds"]))
        return types.CallToolResult(content=[types.TextContent(type="text", text="done")])
    if name == "readonly_trap":
        counter += 1
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(counter))],
            structured_content={"count": counter},
        )
    if name == "call_count":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(counter))],
            structured_content={"count": counter},
        )
    if name == "secret_echo":
        value = args["token"]
        print(f"fixture stderr Bearer {value}", file=sys.stderr, flush=True)
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Bearer {value}")],
            structured_content={"token": value, "nested": {"secret": value}},
        )
    if name == "wrong_output":
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="wrong")],
            structured_content={"count": "not-an-integer"},
        )
    if name == "changing":
        value = args["message"]
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=str(value))],
            structured_content={"message": value},
        )
    if name == "remote_ref":
        counter += 1
        return types.CallToolResult(
            content=[types.TextContent(type="text", text="must not execute")],
            structured_content={"message": "must not execute"},
        )
    return types.CallToolResult(
        content=[types.TextContent(type="text", text="unknown")], is_error=True
    )


async def run(mode: str) -> None:
    global MODE
    MODE = mode
    if mode == "hang-initialize":
        await anyio.sleep(10)
    server = Server(
        "mcp-breakbench-fixture", version="0.1.0", on_list_tools=list_tools, on_call_tool=call_tool
    )
    options = InitializationOptions(
        server_name=server.name,
        server_version=server.version,
        capabilities=server.get_capabilities(NotificationOptions(), {}),
    )
    async with stdio_server() as (read, write):
        await server.run(read, write, options)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=["healthy", "baseline", "current", "hang-initialize", "hang-list", "paginate"],
        default="healthy",
    )
    args = parser.parse_args()
    asyncio.run(run(args.mode))


MODE = "healthy"
if __name__ == "__main__":
    main()
