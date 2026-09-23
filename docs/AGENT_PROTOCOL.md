# Codex–Claude–Bob Coordination Protocol

## Purpose

This protocol lets Codex, Claude Code, and Bob Shell exchange independent opinions, implementation handoffs, reviews, and verification results without relying on hidden chat state. The coordinator is the transport; the repository is the source of truth.

## Roles

- **Coordinator:** starts processes, records events, enforces timeouts, and advances the state machine. It never decides whether code is correct.
- **Implementer:** changes the working tree, runs checks, and produces a structured handoff.
- **Reviewers:** the two non-implementing peers independently inspect the actual diff and test results in parallel. They do not edit.
- **Peer consultant:** analyzes the objective independently before implementation. All three agents consult in parallel.

The user activates the coordinator explicitly. The coordinator is neutral and does not become a fourth engineering authority. Codex, Claude, and Bob receive equivalent working-tree access and are equally eligible for every role. Automatic assignment chooses the first implementer without a permanent product preference; the user can override it with `--first codex`, `--first claude`, or `--first bob`. If either reviewer requests changes, implementation rotates to the next peer. This makes every agent consume and improve peer work while keeping writes serialized.

Approval is unanimous: both reviewers must return `APPROVED`. A single `CHANGES_REQUESTED` keeps the loop active, and a concrete `BLOCKED` verdict stops it.

Coordinator-generated prompts never activate another coordinator. Nested loops are forbidden.

## State machine

```text
CREATED
   |
   v
PARALLEL_CONSULTATION
   |
   v
IMPLEMENTING(round N) --> REVIEWING(two peers, round N) --> UNANIMOUS APPROVAL --> COMPLETE
        ^                                  |
        |                                  +--> ANY BLOCKED --> BLOCKED
        +------- ANY CHANGES_REQUESTED
        |
        +------- round limit reached --> MAX_ROUNDS

Any agent execution failure or timeout --> FAILED
```

The loop completes only when both reviewers approve unanimously. It stops without approval when either reviewer reports a concrete blocker, an agent command fails, a timeout occurs, or the round limit is reached.

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
- Produces three independent approaches, risks, proposed checks, and open questions.

### Implementation

- Receives the objective, all three consultations, and the latest pair of reviews.
- May edit the working tree.
- Must inspect current files rather than assuming the previous handoff is accurate.
- Must run relevant checks and report exact outcomes.

### Review

- Both non-implementing peers receive the objective and implementation handoff.
- Must inspect the actual working tree and diff.
- May run read-only checks and tests but must not modify files.
- Must return one final verdict line defined in `AGENTS.md`.
- Runs in parallel with the other reviewer; reviewers do not see or influence each other's verdict before responding.

## Conflict and failure handling

- Never run two implementation turns at the same time in one working tree.
- If unrelated dirty files exist, preserve them and constrain edits to the assignment.
- If an agent exits nonzero or times out, persist its output and mark the session failed.
- Agent identity never grants extra authority. A read-only constraint follows the reviewer role, and write access follows the implementer role.
- If a response lacks a valid review verdict, treat it as `CHANGES_REQUESTED`; ambiguity is not approval.
- If the round limit is reached, leave the session as `MAX_ROUNDS` and preserve the latest pair of reviews for a future run.

## Security boundary

The coordinator deliberately starts all three CLIs without interactive approvals. This is suitable only for trusted local repositories or external sandboxes. The no-prompt mode does not authorize work outside the user's objective. Agents must still obey repository scope, protect secrets, and avoid destructive operations.

## Human recovery

Inspect the latest session with:

```bash
python3 -m agent_loop status
```

Then either fix the blocker manually or start a new run whose objective references the latest session. Runtime transcripts are local by default and must be reviewed before sharing.
