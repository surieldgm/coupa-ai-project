# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A coding evaluation template for AI engineer candidates. Candidates fork this repo and build a supplier-facing accounts receivable agent on top of a mock procurement API. The agent uses the OpenAI Responses API with raw tool-calling — no frameworks (LangChain, etc.).

## Commands

```bash
# Start the mock API (required before running the agent)
uvicorn api.main:app --reload

# Run the agent
python -m agent.main

# Lint
python3 -m ruff check .

# Type check
python3 -m mypy agent/ --ignore-missing-imports

## Architecture

Two independent components:

**`api/`** — FastAPI mock procurement system. In-memory data (resets on restart), no database. All data is defined in `api/data.py`. Routes are in `api/routers/`. The OpenAPI spec at `/docs` is auto-generated and can be used for tool discovery.

**`agent/`** — Supplier AR agent using OpenAI Responses API (`client.responses.create()`). The architecture:
- `agent/main.py` — Agent loop: user input → model call → tool execution → repeat until text response
- `agent/tools.py` — Tool registry (name→function map), schema list, and `execute_tool_call()` dispatcher
- `agent/procurement_tools/` — One tool per module. `invoices.py` is fully implemented as the reference pattern; other files are stubs with function signatures only

The pattern: each tool module exports a schema dict (OpenAI function format) and an implementation function that calls the API via httpx and returns a JSON string.

