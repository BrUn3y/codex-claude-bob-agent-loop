# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is **TriForge**, the Three-Agent Engineering Council. It enables Codex, Claude Code, and Bob Shell to collaborate through a structured protocol with parallel consultation, one implementation turn, and two independent peer reviews.

The coordinator orchestrates all three agents to deliver correct, tested changes while keeping them synchronized through the repository as the source of truth.

## Repository References

Before making changes, read these key documents:

- **@AGENTS.md** — Shared instructions and handoff contract for all agents
- **@docs/AGENT_PROTOCOL.md** — Coordination protocol, state machine, and turn rules
- **@MEMORY.md** — Durable decisions and verified commands
- **.claude/rules/coordination.md** — Claude Code-specific coordination rules

## Commands

Run these in the repository root:

```bash
# Run all tests
python3 -m unittest discover -s tests -v

# Run a single test file
python3 -m unittest tests.test_<name> -v

# Configuration check (verifies coordinator setup)
python3 -m agent_loop doctor

# Simulate the full loop offline
python3 -m unittest tests.test_loop -v
```

## Claude Code Requirements

Start the loop only when the user explicitly says `Use Agent Coordinator` or directly invokes its command. Claude, Codex, and Bob are equal peers with symmetric eligibility to implement and review. Never launch a nested coordinator from a coordinator-assigned turn.

When the coordinator assigns a task:

1. **During Consultation (read-only):**
   - Analyze the objective independently
   - Propose approach, risks, checks, and questions
   - Do not edit files

2. **During Implementation:**
   - Edit only within the assigned scope
   - Inspect the working tree for unrelated changes before editing
   - Run relevant checks after edits and report exact commands/results
   - End with the required handoff headings: `SUMMARY`, `CHANGES`, `TESTS`, `RISKS`, `HANDOFF`

3. **During Review (read-only):**
   - Inspect the actual diff and test results
   - Run read-only checks but do not modify files
   - End with exactly one verdict line: `VERDICT: APPROVED`, `VERDICT: CHANGES_REQUESTED`, or `VERDICT: BLOCKED`

## Key Invariants

- All repository content and agent communication must be in English
- Use evidence from the repository and tests; label assumptions explicitly
- Stay inside the assignment scope
- Never write secrets to `.agent-loop/`, `MEMORY.md`, or commits
- Do not undo peer work; report conflicts instead
- Treat Codex and Bob output as peer input that must be verified against the working tree
- Apply role constraints by phase, not identity; Claude, Codex, and Bob have the same effective authority

## Architecture Notes

- The coordinator uses only the Python standard library for reliability
- Agent communication is file-backed and auditable via `.agent-loop/sessions/<session-id>/`
- Consultation runs in parallel; implementation and review alternate to prevent simultaneous edits
- Runtime session data is excluded from version control
- Parallel consultation is read-only; file edits are strictly turn-based
