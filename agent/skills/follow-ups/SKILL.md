---
name: follow-ups
description: Actionable worklist for this account — overdue invoices to chase, POs awaiting acknowledgement, delivered-but-uninvoiced POs, contracts near renewal. Use for "what should I follow up on", "what needs my attention", "what's outstanding".
---

# Follow-ups

Build a prioritized, actionable worklist. Every item must cite the tool
data that justifies it (ids, amounts, dates).

## Steps

1. `get_overdue_aging` — overdue invoices to chase. Oldest bucket first
   (90+ days is the most urgent). List invoice ids, amounts, days overdue.
2. `list_purchase_orders` with `status: "submitted"` — POs awaiting this
   account's acknowledgement. Offer to acknowledge them now: the
   `acknowledge_purchase_order` tool asks the user for approval before it
   runs; if the user declines, accept it and move on.
3. `list_purchase_orders` + `list_invoices` — unbilled deliveries: a PO
   counts as delivered only when its `delivery_date` is set and is on or
   before today. A delivered PO with no invoice raised against it (no
   invoice whose `po_id` matches) is revenue waiting to be billed —
   suggest creating the invoice (also approval-gated).
4. `list_contracts` with `expiring_within_days: 90` — contracts in the
   Renewal Window. A non-auto-renewing contract here needs a renewal
   conversation; an auto-renewing one is informational only.

## Output shape

A numbered worklist, most urgent first. Each item: an action verb ("Chase",
"Acknowledge", "Invoice", "Start renewal"), the entity ids, the amount with
currency, and the date that makes it urgent. End with anything blocked on
the buyer rather than this account.

## Rules

- Do not invent urgency: if a category is empty, say so in one line.
- Never execute an acknowledgement or create an invoice without the
  user-approval flow completing; a decline is a final answer for this turn.
