"""Analytics tools: server-side aggregation, preferred over model arithmetic."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient
from agent.registry import ToolSpec, function_schema


def _get_overdue_aging(client: ProcurementClient) -> Any:
    return client.overdue_summary()


def _get_invoiced_totals(client: ProcurementClient) -> Any:
    return client.spend_summary()


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

GET_INVOICED_TOTALS = ToolSpec(
    schema=function_schema(
        "get_invoiced_totals",
        "Server-computed totals for your account: total invoiced, total paid, "
        "total outstanding, and invoice count. Always use this instead of adding "
        "invoice amounts yourself — any question about a total invoiced, paid, or "
        "outstanding amount should be answered from these figures.",
        {},
    ),
    fn=_get_invoiced_totals,
)

TOOLS = [GET_OVERDUE_AGING, GET_INVOICED_TOTALS]
