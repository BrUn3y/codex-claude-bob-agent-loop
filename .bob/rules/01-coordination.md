# Bob Shell coordination rules

- Activate the coordinator only when the user explicitly requests `Use Agent Coordinator` or invokes it directly. Never nest coordinator runs.
- Treat Bob Shell, Claude Code, and Codex as equal peers with the same effective authority and symmetric role eligibility.
- Read `AGENTS.md`, `docs/AGENT_PROTOCOL.md`, and `MEMORY.md` before acting on a coordinator prompt.
- Consultation and review phases are read-only.
- Implementation phases may edit only the assigned scope.
- Verify peer claims against the working tree.
- Use the handoff and verdict formats from `AGENTS.md` exactly.
- Never write secrets to `.agent-loop/`, `MEMORY.md`, or a response.
