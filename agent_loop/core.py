"""File-backed coordination between Codex, Claude Code, and Bob Shell."""

from __future__ import annotations

import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from .prompts import consultation_prompt, implementation_prompt, review_prompt, smoke_prompt

VERDICT_PATTERN = re.compile(r"^VERDICT:\s*(APPROVED|CHANGES_REQUESTED|BLOCKED)\s*$", re.MULTILINE)
AGENT_NAMES = ("codex", "claude", "bob")
REQUIRED_FILES = (
    "AGENTS.md",
    "CLAUDE.md",
    "MEMORY.md",
    "docs/AGENT_PROTOCOL.md",
    ".codex/config.toml",
    ".claude/settings.json",
    ".bob/settings.json",
)


class AgentExecutionError(RuntimeError):
    """Raised when an agent process fails or times out."""


@dataclass(frozen=True)
class LoopConfig:
    root: Path
    objective: str
    max_rounds: int = 3
    timeout_seconds: int = 1800
    first_implementer: str = "auto"
    codex_command: tuple[str, ...] = ("codex",)
    claude_command: tuple[str, ...] = ("claude",)
    bob_command: tuple[str, ...] = ("bob",)

    def __post_init__(self) -> None:
        if self.max_rounds < 1:
            raise ValueError("max_rounds must be at least 1")
        if self.timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")
        if self.first_implementer not in {"auto", *AGENT_NAMES}:
            raise ValueError("first_implementer must be 'auto', 'codex', 'claude', or 'bob'")
        if not self.objective.strip():
            raise ValueError("objective cannot be empty")


@dataclass(frozen=True)
class CommandResult:
    agent: str
    response: str
    stdout: str
    stderr: str
    returncode: int
    command: tuple[str, ...]


@dataclass(frozen=True)
class RunOutcome:
    session_id: str
    state: str
    rounds: int
    session_dir: Path
    verdict: str | None = None


@dataclass
class SessionStore:
    root: Path
    objective: str
    session_id: str = field(default_factory=lambda: _new_session_id())
    _sequence: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        self.directory = self.root / ".agent-loop" / "sessions" / self.session_id
        for name in ("prompts", "responses", "logs"):
            (self.directory / name).mkdir(parents=True, exist_ok=True)
        (self.directory / "objective.md").write_text(
            f"# Objective\n\n{self.objective.strip()}\n", encoding="utf-8"
        )
        self.set_state("CREATED", rounds=0)
        self.event("coordinator", "session", "created", {"objective": self.objective})

    def set_state(self, state: str, **extra: object) -> None:
        payload = {
            "session_id": self.session_id,
            "state": state,
            "updated_at": _now(),
            **extra,
        }
        _atomic_json(self.directory / "session.json", payload)

    def event(self, agent: str, phase: str, event_type: str, payload: object) -> None:
        with self._lock:
            self._sequence += 1
            record = {
                "sequence": self._sequence,
                "timestamp": _now(),
                "agent": agent,
                "phase": phase,
                "type": event_type,
                "payload": payload,
            }
            with (self.directory / "transcript.jsonl").open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    def save_turn(self, stem: str, prompt: str, result: CommandResult) -> None:
        (self.directory / "prompts" / f"{stem}.md").write_text(prompt + "\n", encoding="utf-8")
        (self.directory / "responses" / f"{stem}.md").write_text(
            result.response.rstrip() + "\n", encoding="utf-8"
        )
        log = (
            f"COMMAND: {shlex.join(result.command)}\n"
            f"RETURN CODE: {result.returncode}\n\nSTDOUT\n{result.stdout}\n\nSTDERR\n{result.stderr}\n"
        )
        (self.directory / "logs" / f"{stem}.log").write_text(log, encoding="utf-8")
        self.event(result.agent, stem, "response", {"file": f"responses/{stem}.md"})


class AgentRunner:
    def __init__(self, config: LoopConfig):
        self.config = config

    def run(self, agent: str, prompt: str) -> CommandResult:
        output_file: Path | None = None
        if agent == "codex":
            handle = tempfile.NamedTemporaryFile(prefix="agent-loop-codex-", suffix=".txt", delete=False)
            handle.close()
            output_file = Path(handle.name)
            command = (
                *self.config.codex_command,
                "exec",
                "--dangerously-bypass-approvals-and-sandbox",
                "--skip-git-repo-check",
                "--ephemeral",
                "-C",
                str(self.config.root),
                "--output-last-message",
                str(output_file),
                "-",
            )
        elif agent == "claude":
            command = (
                *self.config.claude_command,
                "--print",
                "--dangerously-skip-permissions",
                "--permission-prompts",
                "none",
                "--output-format",
                "text",
            )
        elif agent == "bob":
            command = (
                *self.config.bob_command,
                "--chat-mode",
                "code",
                "--trust",
                "--approval-mode",
                "yolo",
                "--hide-intermediary-output",
                "--output-format",
                "text",
            )
        else:
            raise ValueError(f"Unknown agent: {agent}")

        try:
            completed = subprocess.run(
                command,
                cwd=self.config.root,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=self.config.timeout_seconds,
                check=False,
                env=os.environ.copy(),
            )
            response = completed.stdout.strip()
            if output_file and output_file.exists():
                saved = output_file.read_text(encoding="utf-8").strip()
                if saved:
                    response = saved
            return CommandResult(
                agent=agent,
                response=response,
                stdout=completed.stdout,
                stderr=completed.stderr,
                returncode=completed.returncode,
                command=tuple(command),
            )
        except subprocess.TimeoutExpired as exc:
            stdout = _timeout_text(exc.stdout)
            stderr = _timeout_text(exc.stderr)
            return CommandResult(
                agent=agent,
                response="",
                stdout=stdout,
                stderr=(stderr + f"\nTimed out after {self.config.timeout_seconds} seconds.").strip(),
                returncode=124,
                command=tuple(command),
            )
        finally:
            if output_file:
                output_file.unlink(missing_ok=True)


def run_loop(config: LoopConfig) -> RunOutcome:
    root = config.root.resolve()
    _validate_root(root)
    store = SessionStore(root=root, objective=config.objective)
    runner = AgentRunner(config)

    try:
        store.set_state("PARALLEL_CONSULTATION", rounds=0)
        consultations = _run_consultations(runner, store, config.objective)
        previous_reviews: str | None = None
        implementer = (
            config.first_implementer
            if config.first_implementer != "auto"
            else _auto_first_implementer(store.session_id)
        )
        store.event("coordinator", "assignment", "first_implementer", {"agent": implementer})

        for round_number in range(1, config.max_rounds + 1):
            reviewers = _reviewers(implementer)
            store.set_state("IMPLEMENTING", rounds=round_number, active_agent=implementer)
            implementation = implementation_prompt(
                implementer,
                reviewers,
                config.objective,
                store.session_id,
                round_number,
                consultations,
                previous_reviews,
            )
            implementation_result = runner.run(implementer, implementation)
            store.save_turn(f"round-{round_number:02d}-implement-{implementer}", implementation, implementation_result)
            _ensure_success(implementation_result, config.timeout_seconds)

            store.set_state("REVIEWING", rounds=round_number, active_agents=list(reviewers))
            review_results, review_verdicts = _run_reviews(
                runner,
                store,
                reviewers,
                implementer,
                config.objective,
                round_number,
                implementation_result.response,
            )
            verdict = aggregate_verdicts(review_verdicts)
            store.event(
                "coordinator",
                "review",
                "aggregate_verdict",
                {"round": round_number, "verdict": verdict, "reviews": review_verdicts},
            )

            if verdict == "APPROVED":
                store.set_state("COMPLETE", rounds=round_number, verdict=verdict)
                return RunOutcome(store.session_id, "COMPLETE", round_number, store.directory, verdict)
            if verdict == "BLOCKED":
                store.set_state("BLOCKED", rounds=round_number, verdict=verdict)
                return RunOutcome(store.session_id, "BLOCKED", round_number, store.directory, verdict)

            previous_reviews = _review_bundle(review_results, review_verdicts)
            implementer = _next_implementer(implementer)

        store.set_state("MAX_ROUNDS", rounds=config.max_rounds, verdict="CHANGES_REQUESTED")
        return RunOutcome(
            store.session_id,
            "MAX_ROUNDS",
            config.max_rounds,
            store.directory,
            "CHANGES_REQUESTED",
        )
    except Exception as exc:
        store.event("coordinator", "session", "failure", {"error": str(exc)})
        store.set_state("FAILED", error=str(exc))
        raise


def run_smoke_test(config: LoopConfig) -> dict[str, bool]:
    """Call all live CLIs concurrently and validate their handshake tokens."""
    _validate_root(config.root.resolve())
    runner = AgentRunner(config)
    responses: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=len(AGENT_NAMES), thread_name_prefix="agent-smoke") as pool:
        futures = {pool.submit(runner.run, agent, smoke_prompt(agent)): agent for agent in AGENT_NAMES}
        for future in as_completed(futures):
            agent = futures[future]
            result = future.result()
            _ensure_success(result, config.timeout_seconds)
            responses[agent] = result.response.strip()
    return {agent: response == f"AGENT_LOOP_READY {agent}" for agent, response in responses.items()}


def parse_verdict(response: str) -> str:
    matches = VERDICT_PATTERN.findall(response)
    final_line = response.rstrip().splitlines()[-1] if response.rstrip() else ""
    final_match = VERDICT_PATTERN.fullmatch(final_line)
    if len(matches) != 1 or final_match is None:
        return "CHANGES_REQUESTED"
    return final_match.group(1)


def aggregate_verdicts(verdicts: dict[str, str]) -> str:
    """Require unanimous approval while preserving any concrete blocker."""
    values = tuple(verdicts.values())
    if "BLOCKED" in values:
        return "BLOCKED"
    if values and all(value == "APPROVED" for value in values):
        return "APPROVED"
    return "CHANGES_REQUESTED"


def command_from_env(variable: str, default: str) -> tuple[str, ...]:
    value = os.environ.get(variable, default)
    parts = tuple(shlex.split(value))
    if not parts:
        raise ValueError(f"{variable} cannot be empty")
    return parts


def doctor(root: Path, commands: Iterable[tuple[str, tuple[str, ...]]]) -> dict[str, object]:
    root = root.resolve()
    files = {name: (root / name).is_file() for name in REQUIRED_FILES}
    binaries: dict[str, dict[str, object]] = {}
    for name, command in commands:
        executable = shutil.which(command[0])
        entry: dict[str, object] = {"found": executable is not None, "path": executable}
        if executable:
            result = subprocess.run(
                (*command, "--version"), capture_output=True, text=True, timeout=15, check=False
            )
            entry["version"] = (result.stdout or result.stderr).strip().splitlines()[0]
            entry["working"] = result.returncode == 0
        binaries[name] = entry
    git = subprocess.run(
        ("git", "rev-parse", "--show-toplevel"), cwd=root, capture_output=True, text=True, check=False
    )
    return {
        "root": str(root),
        "files": files,
        "binaries": binaries,
        "git_repository": git.returncode == 0,
        "ok": all(files.values())
        and all(bool(item.get("working")) for item in binaries.values())
        and git.returncode == 0,
    }


def latest_session(root: Path) -> dict[str, object] | None:
    sessions = root.resolve() / ".agent-loop" / "sessions"
    candidates = sorted((path for path in sessions.glob("*") if path.is_dir()), reverse=True)
    if not candidates:
        return None
    state_file = candidates[0] / "session.json"
    if not state_file.is_file():
        return {"session_id": candidates[0].name, "state": "UNKNOWN", "directory": str(candidates[0])}
    payload = json.loads(state_file.read_text(encoding="utf-8"))
    payload["directory"] = str(candidates[0])
    return payload


def _run_consultations(runner: AgentRunner, store: SessionStore, objective: str) -> dict[str, str]:
    prompts = {
        agent: consultation_prompt(agent, objective, store.session_id) for agent in AGENT_NAMES
    }
    results: dict[str, CommandResult] = {}
    with ThreadPoolExecutor(max_workers=len(AGENT_NAMES), thread_name_prefix="agent-consult") as pool:
        futures = {pool.submit(runner.run, agent, prompts[agent]): agent for agent in prompts}
        for future in as_completed(futures):
            agent = futures[future]
            results[agent] = future.result()
    for agent in AGENT_NAMES:
        store.save_turn(f"consult-{agent}", prompts[agent], results[agent])
    for agent in AGENT_NAMES:
        _ensure_success(results[agent], runner.config.timeout_seconds)
    return {agent: results[agent].response for agent in AGENT_NAMES}


def _run_reviews(
    runner: AgentRunner,
    store: SessionStore,
    reviewers: tuple[str, ...],
    implementer: str,
    objective: str,
    round_number: int,
    handoff: str,
) -> tuple[dict[str, CommandResult], dict[str, str]]:
    prompts = {
        reviewer: review_prompt(
            reviewer,
            implementer,
            objective,
            store.session_id,
            round_number,
            handoff,
        )
        for reviewer in reviewers
    }
    results: dict[str, CommandResult] = {}
    with ThreadPoolExecutor(max_workers=len(reviewers), thread_name_prefix="agent-review") as pool:
        futures = {
            pool.submit(runner.run, reviewer, prompts[reviewer]): reviewer for reviewer in reviewers
        }
        for future in as_completed(futures):
            reviewer = futures[future]
            results[reviewer] = future.result()
    verdicts: dict[str, str] = {}
    for reviewer in reviewers:
        store.save_turn(
            f"round-{round_number:02d}-review-{reviewer}", prompts[reviewer], results[reviewer]
        )
    for reviewer in reviewers:
        _ensure_success(results[reviewer], runner.config.timeout_seconds)
        verdicts[reviewer] = parse_verdict(results[reviewer].response)
        store.event(
            reviewer,
            "review",
            "verdict",
            {"round": round_number, "verdict": verdicts[reviewer]},
        )
    return results, verdicts


def _reviewers(implementer: str) -> tuple[str, ...]:
    return tuple(agent for agent in AGENT_NAMES if agent != implementer)


def _next_implementer(current: str) -> str:
    return AGENT_NAMES[(AGENT_NAMES.index(current) + 1) % len(AGENT_NAMES)]


def _review_bundle(
    results: dict[str, CommandResult], verdicts: dict[str, str]
) -> str:
    return "\n\n".join(
        f"{reviewer.upper()} REVIEW ({verdicts[reviewer]})\n{results[reviewer].response}"
        for reviewer in AGENT_NAMES
        if reviewer in results
    )


def _auto_first_implementer(session_id: str) -> str:
    """Choose a peer without permanently privileging one product."""
    entropy = session_id.rsplit("-", 1)[-1]
    return AGENT_NAMES[int(entropy, 16) % len(AGENT_NAMES)]


def _ensure_success(result: CommandResult, timeout_seconds: int) -> None:
    if result.returncode == 124:
        raise AgentExecutionError(f"{result.agent} exceeded the {timeout_seconds}-second timeout")
    if result.returncode != 0:
        raise AgentExecutionError(
            f"{result.agent} exited with status {result.returncode}: {result.stderr.strip()}"
        )
    if not result.response:
        raise AgentExecutionError(f"{result.agent} returned an empty response")


def _timeout_text(value: str | bytes | None) -> str:
    if value is None:
        return ""
    return value.decode(errors="replace") if isinstance(value, bytes) else value


def _validate_root(root: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (root / name).is_file()]
    if missing:
        raise ValueError(f"Not an agent-loop template root; missing: {', '.join(missing)}")


def _new_session_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid4().hex[:8]}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as handle:
        json.dump(payload, handle, indent=2, ensure_ascii=False)
        handle.write("\n")
        temporary = Path(handle.name)
    temporary.replace(path)
