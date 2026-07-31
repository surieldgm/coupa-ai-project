"""Contract tools."""

from __future__ import annotations

from typing import Any

from agent.procurement import ProcurementClient, ProcurementError, ensure_choice
from agent.registry import ToolSpec, function_schema


def _list_contracts(
    client: ProcurementClient,
    *,
    status: str | None = None,
    expiring_within_days: int | None = None,
) -> Any:
    ensure_choice(status, ("active", "expired", "pending_renewal"), "status")
    if expiring_within_days is not None and expiring_within_days < 1:
        raise ProcurementError("invalid_args", "expiring_within_days must be >= 1")
    return client.list_contracts(status=status, expiring_within_days=expiring_within_days)


LIST_CONTRACTS = ToolSpec(
    schema=function_schema(
        "list_contracts",
        "List the contracts on your account, optionally filtered. Contracts carry "
        "an annual_value; there is no monthly figure stored. WARNING: the "
        "expiring_within_days filter has no lower bound — it returns every "
        "non-expired contract ending on or before the cutoff, including ones "
        "whose end_date is already in the past. Always check each end_date "
        "against today before calling a contract 'expiring soon'.",
        {
            "status": {
                "type": ["string", "null"],
                "description": "Filter by status: active, expired, or pending_renewal. "
                "Null for all.",
            },
            "expiring_within_days": {
                "type": ["integer", "null"],
                "description": "Only non-expired contracts ending within this many days "
                "from today. Null for no expiry filter.",
            },
        },
    ),
    fn=_list_contracts,
)

TOOLS = [LIST_CONTRACTS]
