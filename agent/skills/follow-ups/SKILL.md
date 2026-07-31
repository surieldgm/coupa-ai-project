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
3. `list_purchase_orders` (no status filter) + `list_invoices` (no status
   filter) — deliveries awaiting payment. Do this cross-reference
   explicitly, PO by PO; it is the step most often skipped:
   - Keep only POs where `delivery_date` is set and is on or before today
     (the Delivered rule). Ignore PO status here — acknowledged POs count.
   - For each delivered PO, look for an invoice whose `po_id` equals that
     PO's id **and** whose status is `paid`.
   - Write out the comparison first: PO id → matching invoice id and
     status, or "none".
   - Then report **two separate categories**, each naming its PO ids:
     **(a) Delivered, not invoiced** — no invoice references the PO.
     Revenue waiting to be billed; suggest creating the invoice
     (approval-gated).
     **(b) Delivered, invoiced, not yet paid** — an invoice exists but
     none with status `paid`. Money owed; give the PO id and invoice id.
   - Report each category separately even when one is empty. Never let
     "(a) is empty" stand in for both — a delivered PO with an unpaid
     invoice still needs chasing.
4. `list_contracts` with `expiring_within_days: 90` — candidates for the
   Renewal Window. The filter has no lower bound, so it also returns
   contracts that ended long ago: keep only those whose `end_date` is
   between today and 90 days from today. A contract whose `end_date` has
   already passed is lapsed, not expiring — report it that way. A
   non-auto-renewing contract genuinely in the window needs a renewal
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
