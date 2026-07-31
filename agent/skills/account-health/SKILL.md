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
2. `get_invoiced_totals` — the account-level figures (total invoiced,
   paid, outstanding). Always state the total invoiced amount in the
   summary; these server-computed numbers are the ones to quote.
3. `list_invoices` — the invoice mix behind those totals. Report counts
   and per-item amounts in three groups: **paid**, **overdue**, and
   **pending (not yet due)**. An invoice whose stored status is `pending`
   but whose due date has passed belongs in the overdue group — the
   groups must agree with the overdue set from step 4.
4. `get_overdue_aging` — overdue totals and aging buckets. Use these
   server-computed figures verbatim; never sum overdue invoices yourself.
5. `list_contracts` — contract runway: status, end dates, annual values.
   Compare each `end_date` to today yourself: a date already past means
   the contract has lapsed (say so), while one within the next 90 days
   and not auto-renewing is a Renewal Window risk.
6. `list_purchase_orders` — pipeline state: POs with status `submitted`
   are awaiting acknowledgement. Then cross-reference deliveries against
   invoices explicitly: for every PO whose `delivery_date` is set and on
   or before today, find the invoice whose `po_id` matches and check
   whether it is `paid`. Write out that PO → invoice mapping, then report
   delivered POs with no invoice and delivered POs whose invoice is not
   paid as two separate groups, **naming the PO ids in each**. Only report
   a group empty after checking each delivered PO individually — and never
   let an empty first group stand in for the second: a delivered PO with
   an unpaid invoice is still money owed and must be named.

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
- Every count you state must match the list you show: if you say "3 POs",
  three ids follow. Derive counts from your own lists, not from memory.
- If a comparison against a monthly figure is needed, the only sanctioned
  derivation is Monthly Contract Value = annual_value / 12 — show the division.
- If asked about other suppliers' health, remind the user you can only see
  this account, then summarize this account.
