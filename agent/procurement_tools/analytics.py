"""Analytics tools: server-side aggregation, preferred over model arithmetic."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient
from agent.registry import ToolSpec, function_schema


def _get_overdue_aging(client: ProcurementClient) -> Any:
    return client.overdue_summary()


GET_OVERDUE_AGING = ToolSpec(
    schema=function_schema(
        "get_overdue_aging",
        "Summary of your currently overdue invoices with aging buckets (1-30, "
        "31-60, 61-90, 90+ days), counts, and totals. Prefer this over summing "
        "invoices yourself.",
        {},
    ),
    fn=_get_overdue_aging,
)

TOOLS = [GET_OVERDUE_AGING]
