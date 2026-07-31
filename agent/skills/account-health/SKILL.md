---
name: account-health
description: Full AR health summary of this account — invoice mix, overdue aging, contract runway, PO pipeline, named risk signals. Use for "how is my account doing", "account health", "summary of my standing", "any red flags".
---

# Account health

Produce a grounded health summary of the account. Every number must come
from a tool result in this conversation — fetch fresh, do not answer from
memory.

## Steps

1. `get_my_account` — payment terms and standing (rating, status).
2. `list_invoices` — the full invoice mix. Report counts and per-item
   amounts by status (pending / paid / overdue). Show the items behind any
   total you state.
3. `get_overdue_aging` — overdue totals and aging buckets. Use these
   server-computed figures verbatim; never sum overdue invoices yourself.
4. `list_contracts` — contract runway: status, end dates, annual values.
   Flag any non-auto-renewing contract ending within 90 days (the Renewal
   Window).
5. `list_purchase_orders` — pipeline state: POs with status `submitted`
   are awaiting acknowledgement; note POs whose `delivery_date` is set and
   in the past but that have no corresponding invoice.

## Output shape

A short prose summary, then a **Signals** list. Emit only signals the data
supports, each with severity (info / warning / critical) and its grounding
numbers:

- `AGING_CONCENTRATION` — significant overdue value in the 61-90 or 90+ buckets.
- `RENEWAL_RISK` — a contract in the Renewal Window without auto-renew.
- `UNACKNOWLEDGED_POS` — submitted POs awaiting acknowledgement.
- `UNBILLED_DELIVERIES` — delivered POs with no invoice raised.
- `HEALTHY` — none of the above apply.

## Rules

- State the currency with every amount.
- If a comparison against a monthly figure is needed, the only sanctioned
  derivation is Monthly Contract Value = annual_value / 12 — show the division.
- If asked about other suppliers' health, remind the user you can only see
  this account, then summarize this account.
