# Assignment: Supplier AR Agent

**Time limit:** 6 hours

## Overview

You're building a supplier-facing accounts receivable agent. A working scaffold is provided — one tool (`get_invoices`) is fully implemented to demonstrate the pattern. Your job is to extend the agent into something genuinely useful.

This is a progression. You won't finish everything in 6 hours, and that's intentional. Go as far as you can, but prioritize quality over coverage. We'd rather see three well-built things than six half-finished ones.

## How You'll Be Evaluated

After submission, we'll review your code and schedule a 30-minute conversation where you'll walk us through your implementation and reasoning. You should be able to explain and defend every line you ship.

**Priority-ordered criteria:**

1. **Code quality & defensibility** — Is the code clean, idiomatic, and well-structured? Can you explain why you made the choices you made? We value deliberate, reasoned implementations over speed.

2. **Architectural decisions** — How well does your design extend? Are concerns separated? Is the tool registry well-designed? How do you manage the conversation context window?

3. **Progress through the stages** — How far did you get? This is a signal, not a score. Getting through Stage 2 with excellent code beats completing Stage 4 with brittle code.

4. **Security awareness** — Does the agent enforce supplier tenancy at the application layer? Can the LLM access data outside the configured supplier? How do you handle untrusted input?

5. **Eval design** — If you reach Stage 4, how do you assert on agent behavior? Do you test tool invocation, response accuracy, or both? How do you handle non-determinism?

## The Stages

### Stage 1: Tools

Implement the remaining procurement tools. The stub files in `agent/procurement_tools/` have function signatures and API endpoint documentation. Each tool needs:

- A schema in the Responses API format (see `invoices.py` for the pattern)
- An implementation that calls the mock API via HTTP
- Registration in the tool registry

You decide which tools to implement and how to design the schemas. Not every stub needs to become a tool — think about what a supplier AR agent actually needs.

### Stage 2: Skills

Skills are multi-step workflows that compose multiple tools to answer higher-level questions. For example, a "full AR status" skill might pull a supplier's invoices, check for overdue payments, cross-reference against PO delivery status, and summarize.

How you implement skills is an architectural decision. Some options (not exhaustive):
- Prompt-based: guide the model through multi-step reasoning via system prompts
- Programmatic: orchestrate multiple tool calls in application code
- Hybrid: use the model for reasoning but enforce specific tool-call sequences

### Stage 3: Traces

Instrument your agent loop to produce structured traces. Every conversation turn should generate a trace showing:

- What tools were called, with what arguments, and what they returned
- Token usage and latency
- The model's reasoning chain (what it decided and why)

The format is up to you — JSON lines, a trace viewer, structured logs — but it should be programmatically parseable, not just print statements.

### Stage 4: Evals

Build an evaluation harness that programmatically tests the agent against the question set below. Your harness should:

- Run each question through the agent
- Assert on correctness (however you define that)
- Produce a pass/fail report

How you handle LLM non-determinism, what you assert on (final answer, tool calls, both), and how you structure the harness are all design decisions we'll discuss.

## Evaluation Question Set

These are questions the agent should be able to answer correctly. Use them to guide which tools and skills you build, and as test cases for your eval harness.

**Simple lookups:**
1. What is the status of invoice 2014?
2. What are the payment terms for SteelWorks Manufacturing?
3. What items does QuickShip Logistics have in their catalog?

**Filtering & aggregation:**
4. Which invoices are currently overdue?
5. What is the total pending invoice amount for Pinnacle Consulting Group?
6. Which suppliers have contracts expiring within 90 days?

**Multi-step reasoning:**
7. Does supplier CleanSpace Facilities have any invoices that exceed their monthly contract value?
8. For ByteStream Cloud Services, what's the total invoiced amount vs. their annual contract value?
9. Which purchase orders have been received but don't have a corresponding paid invoice?

**Ambiguous / open-ended:**
10. What should supplier Acme Technology Solutions follow up on?
11. Give me a summary of SteelWorks Manufacturing's account health.
12. Are there any red flags across our supplier relationships?

## Constraints

- **OpenAI Responses API only** — not Chat Completions. Use `client.responses.create()`.
- **No agent frameworks** — no LangChain, LangGraph, CrewAI, etc. Raw tool-use loop.
- **Tools must call the HTTP API** — don't import from `api/` directly.
- **Python only** — use the existing project structure.

## Getting Started

1. Start the mock API: `uvicorn api.main:app --reload`
2. Run the agent: `python -m agent.main`
3. The existing `get_invoices` tool works — try "show me all overdue invoices"
4. Check the OpenAPI docs at `http://localhost:8000/docs` for full endpoint details
5. Read `docs/DATA_MODEL.md` for the entity reference

Good luck.
