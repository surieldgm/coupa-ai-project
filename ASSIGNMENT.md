# Assignment: Supplier AR Agent

**Time limit:** 6 hours (measured from fork to last commit)

## Overview

You're building a supplier-facing accounts receivable agent. A working scaffold is provided with one implemented tool (`get_invoices`) that demonstrates the pattern. Your job is to extend the agent into something genuinely useful.

The stages below are a progression. You won't finish everything, and that's intentional. Prioritize quality over coverage — we'd rather see three well-built things than six half-finished ones.

You're expected to use AI coding tools to accelerate your work. You're also expected to understand and be able to defend every line you ship.

## How You'll Be Evaluated

After submission, we'll review your code and schedule a 30-minute conversation where you walk us through your implementation and reasoning.

**Priority-ordered criteria:**

1. **Code quality & defensibility** — Is the code clean and well-structured? Can you explain why you made the choices you made?
2. **Architectural decisions** — How well does your design extend? Are concerns separated? How do you manage the conversation context window?
3. **Progress through the stages** — How far did you get? This is a signal, not a score.
4. **Security awareness** — Does the agent enforce supplier tenancy at the application layer? Can the LLM access data outside the configured supplier?
5. **Eval design** — If you reach Stage 4, how do you assert on agent behavior? How do you handle non-determinism?

## The Stages

### Stage 1: Tools

You decide which tools to implement and how to design the schemas. Not every stub needs to become a tool — think about what a supplier AR agent actually needs.

### Stage 2: Skills

Skills are multi-step workflows that compose multiple tools to answer higher-level questions. For example, a "full AR status" skill might pull invoices, check for overdue payments, cross-reference against PO delivery status, and summarize. How you implement skills is an architectural decision.

### Stage 3: Traces

Instrument your agent loop to produce structured traces. Every conversation turn should generate a trace that can be analyzed to inform future system improvements. The format is up to you, but it must be programmatically parseable — not just print statements.

### Stage 4: Evals

Build an evaluation harness that programmatically tests the agent against the question set in [`evals/questions.json`](evals/questions.json). Your harness should:

- Run each question through the agent
- Assert on correctness (however you define that)
- Produce a pass/fail report

How you handle non-determinism, what you assert on (final answer, tool calls, both), and how you structure the harness are all design decisions we'll discuss.

## Evaluation Question Set

The questions in [`evals/questions.json`](evals/questions.json) span four categories: simple lookups, filtering & aggregation, multi-step reasoning, and ambiguous/open-ended. **Use them to guide which tools and skills you build, and as test cases if you reach Stage 4.**

## Constraints

- **OpenAI Responses API only** — not Chat Completions. Use `client.responses.create()`.
- **No agent frameworks** — no LangChain, LangGraph, CrewAI, etc. Raw tool-use loop.
- **Tools must call the HTTP API** — don't import from `api/` directly.
- **Don't modify `api/`** — treat it as a standalone service you don't control. Your diff should only touch `agent/` and `evals/`.
- **Python only** — use the existing project structure.
- **Time is measured from fork to last commit.** Commits after 6 hours will not be considered.

## Getting Started

1. Start the mock API: `uvicorn api.main:app --reload`
2. Run the agent: `python -m agent.main`
3. The existing `get_invoices` tool works — try "show me invoices"
4. Check the OpenAPI docs at `http://localhost:8000/docs` for full endpoint details
5. Read `docs/DATA_MODEL.md` for the entity reference

Good luck.
