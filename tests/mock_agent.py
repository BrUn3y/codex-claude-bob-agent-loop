#!/usr/bin/env python3
"""Deterministic fake used to test inter-agent transport without model calls."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 2:
        return 64
    agent = sys.argv[1]
    if "--version" in sys.argv:
        print(f"mock-{agent} 1.0")
        return 0

    if os.environ.get("MOCK_FAIL_AGENT") == agent:
        print("partial stdout before failure")
        print("simulated failure", file=sys.stderr)
        return 7
    if os.environ.get("MOCK_SLEEP_AGENT") == agent:
        time.sleep(2)

    prompt = sys.stdin.read()
    if "peer consultant" in prompt:
        response = f"APPROACH\n{agent} independent plan\nRISKS\nnone\nTESTS\nunit tests\nHANDOFF\nready"
    elif "the IMPLEMENTER for round" in prompt:
        peer_seen = all(
            f"{peer} independent plan" in prompt for peer in ("codex", "claude", "bob")
        )
        previous_seen = "VERDICT: CHANGES_REQUESTED" in prompt
        response = (
            "SUMMARY\nimplemented\nCHANGES\nmock change\nTESTS\npassed\nRISKS\nnone\nHANDOFF\n"
            f"agent={agent};peer_consultations={peer_seen};previous_review={previous_seen}"
        )
    elif "the REVIEWER for round" in prompt:
        round_two = "round 2" in prompt
        if os.environ.get("MOCK_BLOCK_FIRST") == "1":
            verdict = "BLOCKED"
        else:
            verdict = "APPROVED" if round_two or os.environ.get("MOCK_APPROVE_FIRST") == "1" else "CHANGES_REQUESTED"
        response = (
            "SUMMARY\nreviewed\nCHANGES\nnone\nTESTS\npassed\nRISKS\nnone\nHANDOFF\n"
            f"handoff_seen={'peer_consultations=True' in prompt}\nVERDICT: {verdict}"
        )
    elif "communication smoke test" in prompt.lower():
        response = f"AGENT_LOOP_READY {agent}"
    else:
        response = "unexpected prompt"

    if agent == "codex" and "--output-last-message" in sys.argv:
        index = sys.argv.index("--output-last-message")
        Path(sys.argv[index + 1]).write_text(response + "\n", encoding="utf-8")
    print(response)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
