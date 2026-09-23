# Codex–Claude Coordination Protocol

## Purpose

This protocol lets Codex and Claude Code exchange independent opinions, implementation handoffs, reviews, and verification results without relying on hidden chat state. The coordinator is the transport; the repository is the source of truth.

## Roles

- **Coordinator:** starts processes, records events, enforces timeouts, and advances the state machine. It never decides whether code is correct.
- **Implementer:** changes the working tree, runs checks, and produces a structured handoff.
- **Reviewer:** independently inspects the actual diff and test results. It does not edit.
- **Peer consultant:** analyzes the objective independently before implementation. Both agents consult in parallel.

The user activates the coordinator explicitly. The coordinator is neutral and does not become a third engineering authority. Codex and Claude receive equivalent working-tree access and are equally eligible for every role. Automatic assignment chooses the first implementer without a permanent product preference; the user can override it with `--first codex` or `--first claude`. If review requests changes, roles alternate. This makes each agent consume and improve the other agent's work while keeping writes serialized.

Coordinator-generated prompts never activate another coordinator. Nested loops are forbidden.

## State machine

```text
CREATED
   |
   v
PARALLEL_CONSULTATION
   |
   v
IMPLEMENTING(round N) --> REVIEWING(round N) --> APPROVED --> COMPLETE
        ^                         |
        |                         +--> BLOCKED
        +------- CHANGES_REQUESTED
        |
        +------- round limit reached --> MAX_ROUNDS

Any agent execution failure or timeout --> FAILED
```

The loop stops when a reviewer approves, a reviewer reports a concrete blocker, an agent command fails, a timeout occurs, or the round limit is reached.

## Runtime layout

Each run creates an ignored directory:

```text
.agent-loop/sessions/<session-id>/
├── session.json
├── objective.md
├── transcript.jsonl
├── prompts/
├── responses/
└── logs/
```

`transcript.jsonl` is append-only. Every line contains a timestamp, sequence number, phase, agent, event type, and payload. Prompt and response files make a session auditable without committing ephemeral context.

## Turn rules

### Consultation

- Runs concurrently for speed and independent judgment.
- Is strictly read-only.
- Produces approach, risks, proposed checks, and open questions.

### Implementation

- Receives the objective, both consultations, and the latest review.
- May edit the working tree.
- Must inspect current files rather than assuming the previous handoff is accurate.
- Must run relevant checks and report exact outcomes.

### Review

- Receives the objective and implementation handoff.
- Must inspect the actual working tree and diff.
- May run read-only checks and tests but must not modify files.
- Must return one final verdict line defined in `AGENTS.md`.

## Conflict and failure handling

- Never run two implementation turns at the same time in one working tree.
- If unrelated dirty files exist, preserve them and constrain edits to the assignment.
- If an agent exits nonzero or times out, persist its output and mark the session failed.
- Agent identity never grants extra authority. A read-only constraint follows the reviewer role, and write access follows the implementer role.
- If a response lacks a valid review verdict, treat it as `CHANGES_REQUESTED`; ambiguity is not approval.
- If the round limit is reached, leave the session as `MAX_ROUNDS` and preserve the latest review for a future resume.

## Security boundary

The coordinator deliberately starts both CLIs without interactive approvals. This is suitable only for trusted local repositories or external sandboxes. The no-prompt mode does not authorize work outside the user's objective. Agents must still obey repository scope, protect secrets, and avoid destructive operations.

## Human recovery

Inspect the latest session with:

```bash
python3 -m agent_loop status
```

Then either fix the blocker manually or start a new run whose objective references the latest session. Runtime transcripts are local by default and must be reviewed before sharing.
