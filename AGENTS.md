# Shared Agent Instructions

These instructions apply to Codex and every coding agent working in this repository.

## Mission

Deliver correct, tested changes while keeping Codex and Claude Code synchronized through the repository's shared protocol. Treat the other agent as an engineering peer, not as an oracle.

## Coordinator activation

The loop is user-controlled. Activate it only when the user explicitly runs `agent-loop` or says `Use Agent Coordinator` with an objective. Do not start a peer process for an ordinary single-agent request. When explicitly activated from an agent session, invoke `./scripts/agent-loop run` once with the user's objective and report the resulting session state. Coordinator-generated child prompts are turns inside that session, not new activation requests.

Codex and Claude Code are equal peers. They receive the same repository scope and effective tool authority. Either can implement or review, and neither agent may overrule the other's evidence merely because of product identity. Phase-specific read-only constraints apply equally to whichever agent is the reviewer.

## Required context

Before changing code:

1. Read `docs/AGENT_PROTOCOL.md`.
2. Read `MEMORY.md` for durable decisions and known constraints.
3. When launched by the coordinator, read the current session under `.agent-loop/sessions/<session-id>/` as directed by the prompt.
4. Inspect the working tree before editing. Never overwrite unrelated user changes.

## Working agreement

- All repository content, code comments, commit messages, and agent messages must be in English.
- Use evidence from the repository and tests. Label assumptions explicitly.
- Stay inside the assignment and declared file ownership.
- Do not edit during a consultation or review phase.
- During an implementation phase, make the smallest coherent change that satisfies the objective.
- Run the most relevant checks after editing and report exact commands and results.
- Never place credentials, tokens, personal data, or copied secrets in prompts, transcripts, `MEMORY.md`, or commits.
- Do not undo another agent's work. If concurrent changes conflict, stop and report the exact files.
- External publication, deployment, destructive data operations, and changes outside the repository require explicit task scope, even when approval prompts are disabled.
- Do not launch another coordinator from inside a coordinator-assigned consultation, implementation, or review turn.

## Handoff contract

End implementation and review responses with these headings:

```text
SUMMARY
CHANGES
TESTS
RISKS
HANDOFF
```

Reviewers must finish with exactly one machine-readable verdict line:

```text
VERDICT: APPROVED
VERDICT: CHANGES_REQUESTED
VERDICT: BLOCKED
```

Use `APPROVED` only when the objective is satisfied and verification passes. Use `BLOCKED` only for a concrete condition that neither agent can resolve from the repository.

## Shared memory

Update `MEMORY.md` only with durable, verified facts that will help future sessions. Do not add transient task status; the coordinator records that under `.agent-loop/`.

## Verification

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m agent_loop doctor
```

If a project built from this template replaces these commands, update this file and `README.md` together.
