"""Command-line interface for the agent loop."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from .core import (
    AgentExecutionError,
    LoopConfig,
    command_from_env,
    doctor,
    latest_session,
    run_loop,
    run_smoke_test,
)


def parser() -> argparse.ArgumentParser:
    root_parser = argparse.ArgumentParser(
        prog="agent-loop",
        description="Coordinate Codex, Claude Code, and Bob Shell through an auditable loop.",
    )
    root_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    subparsers = root_parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run consultation, implementation, and review turns")
    run.add_argument("objective", nargs="?", help="Engineering objective; omit when using --objective-file")
    run.add_argument("--objective-file", type=Path, help="Read the objective from a UTF-8 file")
    run.add_argument("--max-rounds", type=int, default=3)
    run.add_argument("--timeout", type=int, default=1800, help="Per-agent timeout in seconds")
    run.add_argument("--first", choices=("auto", "codex", "claude", "bob"), default="auto")
    run.add_argument(
        "--live",
        action="store_true",
        help="Stream the human-readable coordination log to stderr",
    )

    subparsers.add_parser("doctor", help="Check files, Git, and all three CLI installations")
    subparsers.add_parser("status", help="Show the latest local coordination session")
    watch = subparsers.add_parser("watch", help="Follow the human-readable log for a session")
    watch.add_argument("--session", default="latest", help="Session ID or 'latest'")
    watch.add_argument("--no-follow", action="store_true", help="Print current content and exit")
    smoke = subparsers.add_parser("smoke-test", help="Run a minimal live handshake with all CLIs")
    smoke.add_argument("--timeout", type=int, default=180)
    return root_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    codex_command = command_from_env("AGENT_LOOP_CODEX_COMMAND", "codex")
    claude_command = command_from_env("AGENT_LOOP_CLAUDE_COMMAND", "claude")
    bob_command = command_from_env("AGENT_LOOP_BOB_COMMAND", "bob")

    try:
        if args.command == "doctor":
            report = doctor(
                root,
                (("codex", codex_command), ("claude", claude_command), ("bob", bob_command)),
            )
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1

        if args.command == "status":
            report = latest_session(root)
            if report is None:
                print("No local agent-loop sessions found.")
                return 1
            print(json.dumps(report, indent=2))
            return 0

        if args.command == "watch":
            return _watch(root, args.session, follow=not args.no_follow)

        if args.command == "smoke-test":
            config = LoopConfig(
                root=root,
                objective="Communication smoke test",
                timeout_seconds=args.timeout,
                codex_command=codex_command,
                claude_command=claude_command,
                bob_command=bob_command,
            )
            report = run_smoke_test(config)
            print(json.dumps(report, indent=2))
            return 0 if report and all(report.values()) else 1

        objective = _objective(args.objective, args.objective_file)
        config = LoopConfig(
            root=root,
            objective=objective,
            max_rounds=args.max_rounds,
            timeout_seconds=args.timeout,
            first_implementer=args.first,
            codex_command=codex_command,
            claude_command=claude_command,
            bob_command=bob_command,
            live=args.live,
        )
        outcome = run_loop(config)
        print(
            json.dumps(
                {
                    "session_id": outcome.session_id,
                    "state": outcome.state,
                    "rounds": outcome.rounds,
                    "verdict": outcome.verdict,
                    "session_dir": str(outcome.session_dir),
                },
                indent=2,
            )
        )
        return 0 if outcome.state == "COMPLETE" else 2
    except (ValueError, AgentExecutionError, OSError) as exc:
        print(f"agent-loop: {exc}", file=sys.stderr)
        return 1


def _objective(inline: str | None, objective_file: Path | None) -> str:
    if bool(inline) == bool(objective_file):
        raise ValueError("Provide exactly one objective argument or --objective-file")
    if objective_file:
        return objective_file.read_text(encoding="utf-8").strip()
    return (inline or "").strip()


def _watch(root: Path, session: str, follow: bool) -> int:
    runtime = root / ".agent-loop"
    if session == "latest":
        pointer = runtime / "latest-session"
        if not pointer.is_file():
            print("agent-loop: no local sessions found", file=sys.stderr)
            return 1
        session = pointer.read_text(encoding="utf-8").strip()
    session_dir = runtime / "sessions" / session
    if not session_dir.is_dir():
        print(f"agent-loop: session not found: {session}", file=sys.stderr)
        return 1

    log_file = session_dir / "live.log"
    position = 0
    terminal_states = {"COMPLETE", "BLOCKED", "MAX_ROUNDS", "FAILED"}
    while True:
        if log_file.is_file():
            with log_file.open("r", encoding="utf-8") as handle:
                handle.seek(position)
                chunk = handle.read()
                position = handle.tell()
            if chunk:
                print(chunk, end="", flush=True)
        if not follow:
            return 0
        state_file = session_dir / "session.json"
        if state_file.is_file():
            state = json.loads(state_file.read_text(encoding="utf-8")).get("state")
            if state in terminal_states:
                return 0
        time.sleep(0.25)
