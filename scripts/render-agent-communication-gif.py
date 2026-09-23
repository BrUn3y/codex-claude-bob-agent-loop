#!/usr/bin/env python3
"""Render the TriForge coordination protocol as an animated terminal GIF."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


WIDTH = 1200
HEIGHT = 675
BACKGROUND = "#07111f"
PANEL = "#0d1b2a"
PANEL_ALT = "#102238"
TEXT = "#e6edf7"
MUTED = "#8192aa"
GREEN = "#4ade80"
COLORS = {
    "COORDINATOR": "#4ade80",
    "CODEX": "#38bdf8",
    "CLAUDE": "#fb923c",
    "BOB": "#c084fc",
}


@dataclass(frozen=True)
class Event:
    time: str
    agent: str
    message: str
    phase: str


EVENTS = (
    Event("00:00:01", "COORDINATOR", "Three-way consultation started", "CONSULT"),
    Event("00:00:03", "CODEX", "Architecture proposal shared", "CONSULT"),
    Event("00:00:04", "CLAUDE", "Risk analysis shared", "CONSULT"),
    Event("00:00:05", "BOB", "Test strategy shared", "CONSULT"),
    Event("00:00:06", "COORDINATOR", "Bob selected as implementer", "IMPLEMENT"),
    Event("00:00:10", "BOB", "Implementation handoff shared", "IMPLEMENT"),
    Event("00:00:11", "COORDINATOR", "Parallel peer review started", "REVIEW"),
    Event("00:00:13", "CODEX", "VERDICT: APPROVED", "REVIEW"),
    Event("00:00:13", "CLAUDE", "VERDICT: APPROVED", "REVIEW"),
    Event("00:00:14", "COORDINATOR", "UNANIMOUS APPROVAL · COMPLETE", "COMPLETE"),
)


def load_font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = (
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/Supplemental/Courier New Bold.ttf" if bold else
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold else
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
        "C:/Windows/Fonts/consolab.ttf" if bold else "C:/Windows/Fonts/consola.ttf",
    )
    for candidate in candidates:
        if Path(candidate).is_file():
            return ImageFont.truetype(candidate, size=size)
    return ImageFont.load_default()


FONT_SMALL = load_font(15)
FONT_BODY = load_font(17)
FONT_BODY_BOLD = load_font(17, bold=True)
FONT_TITLE = load_font(30, bold=True)
FONT_SUBTITLE = load_font(16)
FONT_PHASE = load_font(15, bold=True)
FONT_NODE = load_font(18, bold=True)


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int, fill: str, outline: str | None = None) -> None:
    draw.rounded_rectangle(box, radius=radius, fill=fill, outline=outline, width=1 if outline else 0)


def draw_header(draw: ImageDraw.ImageDraw) -> None:
    draw.text((42, 28), "TriForge", font=FONT_TITLE, fill=TEXT)
    draw.text((220, 39), "LIVE AGENT COUNCIL", font=FONT_SUBTITLE, fill=MUTED)
    rounded(draw, (1014, 27, 1157, 57), 15, "#113122", "#235c3c")
    draw.ellipse((1030, 38, 1040, 48), fill=GREEN)
    draw.text((1050, 34), "STREAMING", font=FONT_PHASE, fill=GREEN)


def draw_terminal(draw: ImageDraw.ImageDraw, visible: int) -> None:
    rounded(draw, (36, 78, 795, 638), 14, PANEL, "#1c3450")
    draw.rectangle((37, 79, 794, 122), fill="#11253a")
    for x, color in ((58, "#ff5f57"), (80, "#febc2e"), (102, "#28c840")):
        draw.ellipse((x - 6, 94, x + 6, 106), fill=color)
    draw.text((132, 90), "triforge · live.log", font=FONT_SMALL, fill=MUTED)
    draw.text((58, 139), "$ agent-loop run --live \"Ship a tested foundation\"", font=FONT_BODY, fill=TEXT)

    y = 178
    start = max(0, visible - 9)
    for event in EVENTS[start:visible]:
        color = COLORS[event.agent]
        draw.text((58, y), event.time, font=FONT_SMALL, fill=MUTED)
        draw.text((150, y), event.agent.ljust(11), font=FONT_BODY_BOLD, fill=color)
        draw.text((286, y), event.message, font=FONT_BODY, fill=TEXT)
        y += 42
    if visible < len(EVENTS):
        draw.rectangle((58, y + 3, 69, y + 23), fill=GREEN)


def node(draw: ImageDraw.ImageDraw, center: tuple[int, int], label: str, color: str, active: bool) -> None:
    x, y = center
    radius = 46 if active else 42
    if active:
        draw.ellipse((x - radius - 7, y - radius - 7, x + radius + 7, y + radius + 7), fill=color + "28")
    draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=PANEL_ALT, outline=color, width=4 if active else 2)
    width = draw.textbbox((0, 0), label, font=FONT_NODE)[2]
    draw.text((x - width / 2, y - 12), label, font=FONT_NODE, fill=color)


def arrow(draw: ImageDraw.ImageDraw, start: tuple[int, int], end: tuple[int, int], color: str, progress: float) -> None:
    draw.line((start, end), fill="#29425f", width=4)
    px = start[0] + (end[0] - start[0]) * progress
    py = start[1] + (end[1] - start[1]) * progress
    draw.ellipse((px - 7, py - 7, px + 7, py + 7), fill=color)


def draw_council(draw: ImageDraw.ImageDraw, event: Event, frame_index: int) -> None:
    rounded(draw, (820, 78, 1164, 638), 14, PANEL, "#1c3450")
    draw.text((848, 101), "COMMUNICATION MAP", font=FONT_PHASE, fill=MUTED)
    rounded(draw, (848, 137, 1136, 174), 18, "#122b43")
    phase_width = draw.textbbox((0, 0), event.phase, font=FONT_PHASE)[2]
    draw.text((992 - phase_width / 2, 147), event.phase, font=FONT_PHASE, fill=GREEN)

    positions = {
        "CODEX": (902, 273),
        "CLAUDE": (1080, 273),
        "BOB": (991, 445),
        "CORE": (991, 344),
    }
    active = {event.agent}
    if event.agent == "COORDINATOR":
        active = {"CORE"}
    if event.phase == "CONSULT":
        source = positions.get(event.agent, positions["CORE"])
        target = positions["CORE"]
    elif event.phase == "IMPLEMENT":
        source = positions.get(event.agent, positions["CORE"])
        target = positions["CORE"]
    elif event.phase == "REVIEW" and event.agent in ("CODEX", "CLAUDE"):
        source = positions["CORE"]
        target = positions[event.agent]
    else:
        source = positions["CORE"]
        target = positions["CORE"]

    for name in ("CODEX", "CLAUDE", "BOB"):
        arrow(draw, positions[name], positions["CORE"], COLORS[name], (frame_index % 4) / 3)
    if source != target:
        arrow(draw, source, target, COLORS.get(event.agent, GREEN), ((frame_index + 2) % 6) / 5)

    node(draw, positions["CODEX"], "CODEX", COLORS["CODEX"], "CODEX" in active)
    node(draw, positions["CLAUDE"], "CLAUDE", COLORS["CLAUDE"], "CLAUDE" in active)
    node(draw, positions["BOB"], "BOB", COLORS["BOB"], "BOB" in active)
    node(draw, positions["CORE"], "LOG", GREEN, "CORE" in active)

    draw.text((853, 536), "SHARED SOURCE OF TRUTH", font=FONT_SMALL, fill=MUTED)
    draw.text((853, 564), "live.log  ·  transcript.jsonl", font=FONT_SMALL, fill=TEXT)
    if event.phase == "COMPLETE":
        rounded(draw, (848, 594, 1136, 622), 14, "#113122", "#235c3c")
        draw.text((883, 599), "✓ UNANIMOUS APPROVAL", font=FONT_PHASE, fill=GREEN)


def render_frame(visible: int, frame_index: int) -> Image.Image:
    image = Image.new("RGB", (WIDTH, HEIGHT), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw_header(draw)
    draw_terminal(draw, visible)
    draw_council(draw, EVENTS[max(0, visible - 1)], frame_index)
    return image


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("assets/triforge-agent-communication.gif"),
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)

    frames = [render_frame(index, index) for index in range(1, len(EVENTS) + 1)]
    durations = [850] * (len(frames) - 1) + [2600]
    frames[0].save(
        args.output,
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
