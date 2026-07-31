"""Tool surface: one module per resource, aggregated here."""

from agent.procurement_tools import (
    account,
    analytics,
    catalog,
    contracts,
    invoices,
    purchase_orders,
)
from agent.registry import ToolSpec

ALL_TOOLS: list[ToolSpec] = [
    *account.TOOLS,
    *invoices.TOOLS,
    *purchase_orders.TOOLS,
    *contracts.TOOLS,
    *catalog.TOOLS,
    *analytics.TOOLS,
]
