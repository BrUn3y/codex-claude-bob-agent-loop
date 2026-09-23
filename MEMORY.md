# Shared Project Memory

This file contains durable, verified knowledge shared by Codex, Claude Code, and Bob Shell. Keep it concise. Task logs belong under `.agent-loop/` and are intentionally not committed.

## Architecture decisions

- The coordinator uses only the Python standard library.
- Agent communication is file-backed and auditable through per-session JSONL transcripts.
- All three consultations run in parallel. One agent implements while the other two review independently in parallel, preventing simultaneous edits to the same working tree.
- Permission bypass is passed explicitly to all three CLIs by the coordinator because repository settings alone cannot reliably enable it for every installation.
- The user explicitly activates the neutral coordinator. Codex, Claude, and Bob are symmetric peers; automatic first-turn assignment does not permanently privilege any product.

## Invariants

- Repository content and agent handoffs are written in English.
- A review phase is read-only.
- Role constraints apply to the current phase, not to agent identity; all three peers have the same effective authority.
- A new implementation round consumes both previous reviews, so no agent works from stale context.
- Runtime session data is stored in `.agent-loop/` and is not committed.
- Secrets are never written to shared memory or transcripts.

## Verified commands

- Unit tests: `python3 -m unittest discover -s tests -v`
- Configuration check: `python3 -m agent_loop doctor`
- Offline loop simulation: `python3 -m unittest tests.test_loop -v`

## Known constraints

- Disabling approval prompts also disables an important safety boundary. Run the live loop only in a repository and machine environment you trust.
- All three CLIs must already be installed and authenticated for a live session.
- A shared working tree cannot safely accept simultaneous edits. Parallel work is limited to read-only consultation and review; editing is turn-based.

## Learning log

Add only dated, durable lessons in this format:

```text
- YYYY-MM-DD — Verified fact and why it matters.
```
