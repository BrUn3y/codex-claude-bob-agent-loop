"""Prompt builders for the explicit coordination protocol."""

from __future__ import annotations

from textwrap import dedent


def consultation_prompt(agent: str, objective: str, session_id: str) -> str:
    return dedent(
        f"""
        You are {agent} acting as a peer consultant in coordination session {session_id}.

        Read AGENTS.md, docs/AGENT_PROTOCOL.md, and MEMORY.md first.
        This phase is READ-ONLY: do not edit files, create commits, or change configuration.
        Inspect the repository as needed and give an independent engineering opinion.

        OBJECTIVE
        {objective}

        Return concise sections named APPROACH, RISKS, TESTS, and HANDOFF.
        Identify assumptions and file boundaries. Do not claim you ran a check unless you ran it.
        """
    ).strip()


def implementation_prompt(
    agent: str,
    reviewers: tuple[str, ...],
    objective: str,
    session_id: str,
    round_number: int,
    consultations: dict[str, str],
    previous_reviews: str | None,
) -> str:
    review_block = previous_reviews or "No previous reviews; this is the first implementation turn."
    reviewer_names = ", ".join(reviewers)
    consultation_block = "\n\n".join(
        f"{name.upper()} CONSULTATION\n{consultations.get(name, 'Unavailable')}"
        for name in ("codex", "claude", "bob")
    )
    return dedent(
        f"""
        You are {agent}, the IMPLEMENTER for round {round_number} of session {session_id}.
        The independent reviewers for this turn are: {reviewer_names}.

        Read AGENTS.md, docs/AGENT_PROTOCOL.md, and MEMORY.md first. Inspect the current working
        tree before editing and preserve unrelated changes. You may edit files in this phase.
        Implement the smallest coherent solution, run relevant checks, and leave the working tree
        ready for review. Verify peer suggestions instead of accepting them blindly.

        OBJECTIVE
        {objective}

        PEER CONSULTATIONS
        {consultation_block}

        PREVIOUS REVIEWS
        {review_block}

        End with exactly these headings: SUMMARY, CHANGES, TESTS, RISKS, HANDOFF.
        In HANDOFF, tell {reviewer_names} what to inspect and list any unresolved concern.
        """
    ).strip()


def review_prompt(
    agent: str,
    implementer: str,
    objective: str,
    session_id: str,
    round_number: int,
    handoff: str,
) -> str:
    return dedent(
        f"""
        You are {agent}, the REVIEWER for round {round_number} of session {session_id}.
        {implementer} produced the handoff below.

        Read AGENTS.md, docs/AGENT_PROTOCOL.md, and MEMORY.md first. This phase is READ-ONLY:
        do not edit files, create commits, or reformat code. Inspect the actual working tree and
        git diff; never approve from the handoff alone. Run relevant non-mutating checks and tests.
        Evaluate correctness, scope, regressions, security, and whether the objective is complete.

        OBJECTIVE
        {objective}

        IMPLEMENTER HANDOFF
        {handoff}

        Report findings with file and line references where possible. End with the headings
        SUMMARY, CHANGES, TESTS, RISKS, HANDOFF, followed by exactly one final line:
        VERDICT: APPROVED
        VERDICT: CHANGES_REQUESTED
        VERDICT: BLOCKED

        Choose only one verdict. APPROVED means the objective is satisfied and verification passes.
        """
    ).strip()


def smoke_prompt(agent: str) -> str:
    token = f"AGENT_LOOP_READY {agent}"
    return dedent(
        f"""
        This is a read-only communication smoke test. Read the repository instructions, do not use
        tools that modify state, and reply with exactly this single line:
        {token}
        """
    ).strip()
