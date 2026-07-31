# MCP-shaped seams, no MCP protocol

We considered integrating MCP for tools and skills and rejected both routes: the Responses API's hosted MCP tool (present in the pinned SDK 1.82.0) requires a publicly reachable server — our stack is localhost — and moves tool execution into OpenAI's loop, which would relocate tenancy injection and the Gated Tool interception out of our application layer; client-side MCP requires the `mcp` SDK, and `requirements.txt` is outside the assignment's allowed diff (`agent/` and `evals/` only), making the dependency set immutable. Instead, the tool registry deliberately mirrors MCP semantics without the protocol: `list_tools()` returns schemas (MCP `tools/list`), `call_tool(name, args)` returns a result envelope (MCP `tools/call`), and `load_skill` mirrors `resources/read`. Adopting real MCP later is a registry-implementation swap; the loop, permission gate, tenancy, and traces are untouched.

## Considered Options

- Hosted MCP tool (`{"type": "mcp", "server_url": ...}`) — rejected: localhost unreachable from OpenAI's infra (demo would depend on a tunnel), and execution leaves our security boundary.
- Client-side MCP host with a local MCP server — rejected: `mcp` SDK not in the pinned, unmodifiable requirements; hand-rolling the protocol in a 6-hour window inverts the quality-over-coverage grading.
- Skills served as MCP resources — rejected: progressive disclosure still needs the same menu + fetch-on-demand pattern; MCP changes only the transport of a file read.
