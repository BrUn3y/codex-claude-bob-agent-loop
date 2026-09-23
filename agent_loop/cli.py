"""Command-line interface for the agent loop."""

from __future__ import annotations

import argparse
import json
import sys
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
        description="Coordinate Codex and Claude Code through an auditable engineering loop.",
    )
    root_parser.add_argument("--root", type=Path, default=Path.cwd(), help="Repository root")
    subparsers = root_parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run consultation, implementation, and review turns")
    run.add_argument("objective", nargs="?", help="Engineering objective; omit when using --objective-file")
    run.add_argument("--objective-file", type=Path, help="Read the objective from a UTF-8 file")
    run.add_argument("--max-rounds", type=int, default=3)
    run.add_argument("--timeout", type=int, default=1800, help="Per-agent timeout in seconds")
    run.add_argument("--first", choices=("auto", "codex", "claude"), default="auto")

    subparsers.add_parser("doctor", help="Check files, Git, and both CLI installations")
    subparsers.add_parser("status", help="Show the latest local coordination session")
    smoke = subparsers.add_parser("smoke-test", help="Run a minimal live handshake with both CLIs")
    smoke.add_argument("--timeout", type=int, default=180)
    return root_parser


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    root = args.root.resolve()
    codex_command = command_from_env("AGENT_LOOP_CODEX_COMMAND", "codex")
    claude_command = command_from_env("AGENT_LOOP_CLAUDE_COMMAND", "claude")

    try:
        if args.command == "doctor":
            report = doctor(root, (("codex", codex_command), ("claude", claude_command)))
            print(json.dumps(report, indent=2))
            return 0 if report["ok"] else 1

        if args.command == "status":
            report = latest_session(root)
            if report is None:
                print("No local agent-loop sessions found.")
                return 1
            print(json.dumps(report, indent=2))
            return 0

        if args.command == "smoke-test":
            config = LoopConfig(
                root=root,
                objective="Communication smoke test",
                timeout_seconds=args.timeout,
                codex_command=codex_command,
                claude_command=claude_command,
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
