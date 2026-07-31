---
name: contract-reconciliation
description: Reconcile invoiced amounts against contract values, and match POs to invoices. Use for "invoices vs contract value", "monthly contract value", "delivered but not paid", "are we billing to contract".
---

# Contract reconciliation

Compare what was invoiced against what the contracts say, and match
purchase orders to their invoices. All arithmetic is shown per item so the
user can verify every figure.

## Steps

1. `list_contracts` — the contract(s): annual value, currency, term dates,
   status. Always report the annual value of every contract you find, even
   if its term has ended or it is pending renewal — "the contract value is
   X, and note the term ended on DATE" is the answer; "there is no
   contract" is wrong whenever a contract record exists.
2. Totals: for "total invoiced / paid / outstanding" use
   `get_invoiced_totals` — the server computes it, and it is the figure to
   quote. Use `list_invoices` for the per-item detail behind that total.
   Only when a question needs a *subset* total (one month, one contract
   term) do you add amounts yourself: list every invoice you are
   including (by `issued_date`), state what you excluded, add them in
   order, and re-check the sum against your own list.
3. Monthly comparisons: the only sanctioned monthly figure is
   **Monthly Contract Value = annual_value / 12**. Show the division
   explicitly (e.g. 120,000 / 12 = 10,000 USD/month) before comparing.
4. PO-to-invoice matching (`list_purchase_orders` + `list_invoices`):
   - A PO counts as delivered only when its `delivery_date` is set and on
     or before today.
   - A PO is paid-for when an invoice with that `po_id` has status `paid`.
   - Report delivered POs with no paid invoice as a matching table:
     PO id, delivery date, amount, invoice status (or "no invoice").

## Output shape

The verdict first (over / under / on contract, or the unmatched-PO list),
then the working: contract figures, the per-item invoice arithmetic, and
the matching table where relevant.

## Rules

- State the currency with every amount; never mix currencies in a sum.
- State period assumptions explicitly; if the user's period is ambiguous,
  say which one you used and why.
- Amounts exceeding a contract are findings, not accusations — report the
  numbers plainly.
