# Supplier AR Agent

A conversational accounts-receivable assistant that suppliers use to inspect and act on their own commercial relationship with the buyer (invoices, purchase orders, contracts, catalog). The mock Procurement API (`api/`) is an external system this context consumes but does not own.

## Language

### Session & Tenancy

**Session**:
One conversation between a supplier user and the agent, bound to exactly one Acting Supplier at creation. Identity is established by the application at session start — never by conversation content.
_Avoid_: chat, thread

**Acting Supplier**:
The supplier a Session is authenticated as. All data the agent reads or writes belongs to the Acting Supplier; the model cannot see, choose, or change it.
_Avoid_: current supplier, tenant id, configured supplier

**Tenancy**:
The guarantee that every API call a Session makes is scoped to its Acting Supplier. Enforced in application code, not by the model or the API.
_Avoid_: security filter, supplier scoping

**Scope-down**:
The agent's posture when asked about data beyond the Acting Supplier: state the boundary, then answer whatever in-tenant portion of the question exists.
_Avoid_: refusal, guardrail response

**Existence Ambiguity**:
The rule that the agent's wording never distinguishes "resource doesn't exist" from "resource exists but belongs to another supplier."
_Avoid_: 404 handling

**Gated Tool**:
A tool with side effects. The Session intercepts it before execution and asks the human to approve the exact action; a decline is returned to the model as an ordinary result. Approval may be remembered for the rest of the Session, per tool.
_Avoid_: dangerous tool, write tool, confirmation parameter

### AR Semantics

**Monthly Contract Value**:
One twelfth of a contract's annual value. The only sanctioned monthly derivation; contracts store annual value only.
_Avoid_: monthly spend, monthly budget

**Effectively Overdue**:
An invoice whose stored status is `overdue`, or whose status is `pending` and whose due date has passed. The buyer's aggregates use this rule, so the agent reports these as overdue rather than pending.
_Avoid_: late, past due, aging

**Delivered PO**:
A purchase order whose delivery date is set and is on or before today. Resolves the API's "expected or actual" ambiguity by decree.
_Avoid_: completed PO, fulfilled order

**Renewal Window**:
The final 90 days before a contract's end date. A non-auto-renewing contract inside it is a follow-up item.
_Avoid_: expiring soon, about to lapse
