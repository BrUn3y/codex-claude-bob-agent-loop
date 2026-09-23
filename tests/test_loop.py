from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_loop.core import (
    AgentExecutionError,
    LoopConfig,
    aggregate_verdicts,
    parse_verdict,
    run_loop,
    run_smoke_test,
)


SOURCE_ROOT = Path(__file__).resolve().parents[1]


class LoopTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        for relative in (
            "AGENTS.md",
            "CLAUDE.md",
            "MEMORY.md",
            "docs/AGENT_PROTOCOL.md",
            ".codex/config.toml",
            ".claude/settings.json",
            ".bob/settings.json",
        ):
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE_ROOT / relative, destination)
        mock = str(SOURCE_ROOT / "tests" / "mock_agent.py")
        self.codex = (sys.executable, mock, "codex")
        self.claude = (sys.executable, mock, "claude")
        self.bob = (sys.executable, mock, "bob")

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def config(self, **overrides: object) -> LoopConfig:
        values = {
            "root": self.root,
            "objective": "Build a verified example.",
            "max_rounds": 3,
            "timeout_seconds": 10,
            "first_implementer": "codex",
            "codex_command": self.codex,
            "claude_command": self.claude,
            "bob_command": self.bob,
        }
        values.update(overrides)
        return LoopConfig(**values)  # type: ignore[arg-type]

    def test_agents_exchange_consultations_and_alternate_after_review(self) -> None:
        outcome = run_loop(self.config())
        self.assertEqual(outcome.state, "COMPLETE")
        self.assertEqual(outcome.rounds, 2)

        response_files = {path.name: path.read_text(encoding="utf-8") for path in (outcome.session_dir / "responses").glob("*.md")}
        self.assertIn("peer_consultations=True", response_files["round-01-implement-codex.md"])
        self.assertIn("VERDICT: CHANGES_REQUESTED", response_files["round-01-review-claude.md"])
        self.assertIn("VERDICT: CHANGES_REQUESTED", response_files["round-01-review-bob.md"])
        self.assertIn("agent=claude", response_files["round-02-implement-claude.md"])
        self.assertIn("previous_review=True", response_files["round-02-implement-claude.md"])
        self.assertIn("VERDICT: APPROVED", response_files["round-02-review-codex.md"])
        self.assertIn("VERDICT: APPROVED", response_files["round-02-review-bob.md"])

        events = [json.loads(line) for line in (outcome.session_dir / "transcript.jsonl").read_text(encoding="utf-8").splitlines()]
        sequences = [event["sequence"] for event in events]
        self.assertEqual(sequences, list(range(1, len(sequences) + 1)))

    def test_live_command_flags_are_present_in_logs(self) -> None:
        outcome = run_loop(self.config(max_rounds=1))
        self.assertEqual(outcome.state, "MAX_ROUNDS")
        self.assertEqual(outcome.verdict, "CHANGES_REQUESTED")
        codex_log = (outcome.session_dir / "logs" / "consult-codex.log").read_text(encoding="utf-8")
        claude_log = (outcome.session_dir / "logs" / "consult-claude.log").read_text(encoding="utf-8")
        bob_log = (outcome.session_dir / "logs" / "consult-bob.log").read_text(encoding="utf-8")
        self.assertIn("--dangerously-bypass-approvals-and-sandbox", codex_log)
        self.assertIn("--dangerously-skip-permissions", claude_log)
        self.assertIn("--permission-prompts none", claude_log)
        self.assertIn("--approval-mode yolo", bob_log)
        self.assertIn("--trust", bob_log)
        self.assertNotIn("--prompt", bob_log)

    def test_smoke_handshake_calls_all_agents(self) -> None:
        self.assertEqual(
            run_smoke_test(self.config()),
            {"codex": True, "claude": True, "bob": True},
        )

    def test_missing_verdict_is_never_approval(self) -> None:
        self.assertEqual(parse_verdict("Looks fine"), "CHANGES_REQUESTED")
        self.assertEqual(parse_verdict("VERDICT: APPROVED\n"), "APPROVED")
        self.assertEqual(
            parse_verdict("VERDICT: CHANGES_REQUESTED\nVERDICT: APPROVED"),
            "CHANGES_REQUESTED",
        )
        self.assertEqual(
            parse_verdict("VERDICT: APPROVED\nTrailing explanation"),
            "CHANGES_REQUESTED",
        )

    def test_failed_agent_output_is_persisted_before_session_fails(self) -> None:
        with patch.dict(os.environ, {"MOCK_FAIL_AGENT": "codex"}):
            with self.assertRaises(AgentExecutionError):
                run_loop(self.config())

        sessions = list((self.root / ".agent-loop" / "sessions").iterdir())
        self.assertEqual(len(sessions), 1)
        session = sessions[0]
        state = json.loads((session / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "FAILED")
        log = (session / "logs" / "consult-codex.log").read_text(encoding="utf-8")
        self.assertIn("partial stdout before failure", log)
        self.assertIn("simulated failure", log)
        self.assertTrue((session / "prompts" / "consult-codex.md").is_file())

    def test_claude_can_implement_first_with_codex_as_reviewer(self) -> None:
        with patch.dict(os.environ, {"MOCK_APPROVE_FIRST": "1"}):
            outcome = run_loop(self.config(first_implementer="claude"))
        self.assertEqual(outcome.state, "COMPLETE")
        self.assertTrue((outcome.session_dir / "responses" / "round-01-implement-claude.md").is_file())
        self.assertTrue((outcome.session_dir / "responses" / "round-01-review-codex.md").is_file())
        self.assertTrue((outcome.session_dir / "responses" / "round-01-review-bob.md").is_file())

    def test_bob_can_implement_first_with_two_peer_reviewers(self) -> None:
        with patch.dict(os.environ, {"MOCK_APPROVE_FIRST": "1"}):
            outcome = run_loop(self.config(first_implementer="bob"))
        self.assertEqual(outcome.state, "COMPLETE")
        self.assertTrue((outcome.session_dir / "responses" / "round-01-implement-bob.md").is_file())
        self.assertTrue((outcome.session_dir / "responses" / "round-01-review-codex.md").is_file())
        self.assertTrue((outcome.session_dir / "responses" / "round-01-review-claude.md").is_file())

    def test_review_aggregation_requires_unanimous_approval(self) -> None:
        self.assertEqual(
            aggregate_verdicts({"claude": "APPROVED", "bob": "APPROVED"}),
            "APPROVED",
        )
        self.assertEqual(
            aggregate_verdicts({"claude": "APPROVED", "bob": "CHANGES_REQUESTED"}),
            "CHANGES_REQUESTED",
        )
        self.assertEqual(
            aggregate_verdicts({"claude": "CHANGES_REQUESTED", "bob": "BLOCKED"}),
            "BLOCKED",
        )

    def test_blocked_verdict_is_a_terminal_state(self) -> None:
        with patch.dict(os.environ, {"MOCK_BLOCK_FIRST": "1"}):
            outcome = run_loop(self.config())
        self.assertEqual(outcome.state, "BLOCKED")
        self.assertEqual(outcome.verdict, "BLOCKED")
        state = json.loads((outcome.session_dir / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "BLOCKED")

    def test_timeout_output_is_persisted_and_session_fails(self) -> None:
        with patch.dict(os.environ, {"MOCK_SLEEP_AGENT": "codex"}):
            with self.assertRaises(AgentExecutionError):
                run_loop(self.config(timeout_seconds=1))

        session = next((self.root / ".agent-loop" / "sessions").iterdir())
        state = json.loads((session / "session.json").read_text(encoding="utf-8"))
        self.assertEqual(state["state"], "FAILED")
        log = (session / "logs" / "consult-codex.log").read_text(encoding="utf-8")
        self.assertIn("Timed out after 1 seconds", log)
        self.assertIn("RETURN CODE: 124", log)


if __name__ == "__main__":
    unittest.main()
