"""Tool registry — an MCP-shaped seam (docs/adr/0002).

list_tools() mirrors MCP tools/list; call_tool() mirrors tools/call.
Adopting real MCP later is an implementation swap behind this interface.

The registry is tenant-bound through its ProcurementClient: no tool
schema exposes a supplier parameter, and no tool implementation can
reach outside the Acting Supplier.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from agent.procurement import ProcurementClient, ProcurementError

OutcomeStatus = Literal["ok", "not_found", "api_error", "invalid_args", "unknown_tool"]


@dataclass(frozen=True)
class ToolSpec:
    schema: dict[str, Any]
    fn: Callable[..., Any]
    gated: bool = False
    summarize: Callable[[dict[str, Any]], str] | None = None


@dataclass(frozen=True)
class ToolOutcome:
    status: OutcomeStatus
    output: str  # JSON envelope, exactly what the model sees


def function_schema(
    name: str, description: str, properties: dict[str, Any]
) -> dict[str, Any]:
    """OpenAI Responses strict function schema: every property required
    (optionals are nullable), no additional properties."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


def error_envelope(kind: str, message: str) -> str:
    return json.dumps({"ok": False, "error": {"type": kind, "message": message}})


class ToolRegistry:
    def __init__(self, client: ProcurementClient, specs: Sequence[ToolSpec]) -> None:
        self._client = client
        self._specs = {spec.schema["name"]: spec for spec in specs}

    @property
    def supplier_id(self) -> int:
        return self._client.supplier_id

    def close(self) -> None:
        self._client.close()

    def list_tools(self) -> list[dict[str, Any]]:
        return [spec.schema for spec in self._specs.values()]

    def is_gated(self, name: str) -> bool:
        spec = self._specs.get(name)
        return spec is not None and spec.gated

    def summarize(self, name: str, args: dict[str, Any]) -> str:
        spec = self._specs.get(name)
        if spec is not None and spec.summarize is not None:
            return spec.summarize(args)
        return f"{name}({json.dumps(args)})"

    def call_tool(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        """Execute a tool. Failures never raise — they become error
        envelopes the model can read and recover from."""
        spec = self._specs.get(name)
        if spec is None:
            return ToolOutcome("unknown_tool", error_envelope("unknown_tool", f"unknown tool: {name}"))
        try:
            data = spec.fn(self._client, **args)
        except TypeError as exc:
            return ToolOutcome("invalid_args", error_envelope("invalid_args", f"invalid arguments: {exc}"))
        except ProcurementError as exc:
            return ToolOutcome(exc.kind, error_envelope(exc.kind, exc.message))
        except Exception as exc:  # noqa: BLE001 — FR1.7: no tool failure may crash the turn
            return ToolOutcome("api_error", error_envelope("api_error", f"tool failed: {exc}"))
        return ToolOutcome("ok", json.dumps({"ok": True, "data": data}, default=str))
