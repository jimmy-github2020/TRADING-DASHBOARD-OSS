from __future__ import annotations

import inspect
import json
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Any
from typing import get_args, get_type_hints

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from ai_tools import (
    get_daily_notes,
    get_market_summary,
    get_news_headlines,
    get_sentiment_data,
    get_technical_signals,
)

ToolHandler = Callable[..., Awaitable[dict[str, Any]]]


class ToolCallRequest(BaseModel):
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class MCPServer:
    def __init__(self, name: str) -> None:
        self.name = name
        self._tools: dict[str, dict[str, Any]] = {}

    def tool(self, *, name: str | None = None, description: str) -> Callable[[ToolHandler], ToolHandler]:
        def decorator(func: ToolHandler) -> ToolHandler:
            tool_name = name or func.__name__
            self._tools[tool_name] = {
                "name": tool_name,
                "description": description,
                "parameters": self._build_parameters_schema(func),
                "handler": func,
            }
            return func

        return decorator

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": tool["name"],
                "description": tool["description"],
                "parameters": tool["parameters"],
            }
            for tool in self._tools.values()
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(name)
        handler = tool["handler"]
        return await handler(**arguments)

    @staticmethod
    def _build_parameters_schema(func: ToolHandler) -> dict[str, Any]:
        signature = inspect.signature(func)
        type_hints = get_type_hints(func)
        properties: dict[str, Any] = {}
        required: list[str] = []

        for name, parameter in signature.parameters.items():
            annotation = type_hints.get(name, parameter.annotation)
            schema_type = "string"
            annotation_args = get_args(annotation)
            if annotation is int or int in annotation_args:
                schema_type = "integer"
            elif annotation is float or float in annotation_args:
                schema_type = "number"
            elif annotation is bool or bool in annotation_args:
                schema_type = "boolean"

            field_schema: dict[str, Any] = {"type": schema_type}
            if parameter.default is not inspect.Parameter.empty:
                field_schema["default"] = parameter.default
            else:
                required.append(name)
            properties[name] = field_schema

        return {"type": "object", "properties": properties, "required": required}


server = MCPServer(name="trading-dashboard")
router = APIRouter(prefix="/mcp", tags=["mcp"])


@server.tool(name="get_market_summary", description="取得大盤指數最新收盤、漲跌幅、成交量")
async def tool_get_market_summary(scope: str = "tw") -> dict[str, Any]:
    return await get_market_summary(scope=scope)


@server.tool(name="get_technical_signals", description="取得 RSI / MACD / KD 數值與多空訊號")
async def tool_get_technical_signals(scope: str = "tw") -> dict[str, Any]:
    return await get_technical_signals(scope=scope)


@server.tool(name="get_sentiment_data", description="取得 Fear & Greed 指數、VIX、Put-Call Ratio")
async def tool_get_sentiment_data(scope: str = "tw") -> dict[str, Any]:
    return await get_sentiment_data(scope=scope)


@server.tool(name="get_news_headlines", description="取得今日重要新聞標題與 NLP 情緒評分")
async def tool_get_news_headlines(scope: str = "tw", limit: int = 5) -> dict[str, Any]:
    return await get_news_headlines(scope=scope, limit=limit)


@server.tool(name="get_daily_notes", description="取得使用者當日投資筆記")
async def tool_get_daily_notes(date: str | None = None) -> dict[str, Any]:
    return await get_daily_notes(date=date)


def _tool_list_payload() -> dict[str, Any]:
    return {"name": server.name, "transport": "sse", "tools": server.list_tools()}


@router.get("")
async def get_mcp_tool_list() -> dict[str, Any]:
    return _tool_list_payload()


@router.get("/")
async def get_mcp_tool_list_slash() -> dict[str, Any]:
    return _tool_list_payload()


@router.get("/tools")
async def get_mcp_tools() -> dict[str, Any]:
    return _tool_list_payload()


@router.get("/sse")
async def get_mcp_sse() -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        yield f"event: tools\ndata: {json.dumps(_tool_list_payload(), ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/call")
async def call_mcp_tool(request: ToolCallRequest) -> dict[str, Any]:
    try:
        result = await server.call_tool(request.name, request.arguments)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown MCP tool: {request.name}") from exc
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"name": request.name, "result": result}
