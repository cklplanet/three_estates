#!/usr/bin/env python3
"""Rebuild per-character logs from one canonical detailed dialogue log."""

from __future__ import annotations

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = PROJECT_ROOT / "three_estates_sim" / "backend_server"
sys.path.insert(0, str(BACKEND_ROOT))

from utils import safe_log_filename  # noqa: E402


DIALOGUE_RE = re.compile(
    r"^\[(?P<time>[^\]]+)\] (?P<label>\S+) "
    r"\((?P<table>[^)]+)\) (?P<speaker>.*?) -> (?P<target>.*?) "
    r"\[(?P<meta>[^\]]+)\]: (?P<payload>.*) "
    r"\| (?P<audience_label>audience|听众|聞き手)=\[(?P<audience>.*)\]$"
)
EVENT_RE = re.compile(
    r"^\[[^\]]+\] \S+ \([^)]+\) (?P<speaker>.*?) -> "
    r"(?P<target>.*?): .*?(?: \| keywords=(?P<keywords>.*))?$"
)
ACTION_PREFIX_RE = re.compile(r"^\([^)]*\)\s*")
SCREAM_VOLUMES = {
    "practically screaming",
    "近乎喊叫",
    "ほとんど叫び声",
}


def split_names(value):
    return {part.strip() for part in value.split(", ") if part.strip()}


def overheard_table_label(dialogue_label, table):
    if dialogue_label == "对白":
        return f"从{table}听见"
    if dialogue_label == "会話":
        return f"{table}から聞こえた"
    return f"overheard from {table}"


def unique_filename_map(names):
    result = {}
    used = {}
    for name in sorted(names):
        base = safe_log_filename(name)
        filename = base
        counter = 2
        while filename in used and used[filename] != name:
            filename = f"{base}_{counter}"
            counter += 1
        used[filename] = name
        result[name] = filename
    return result


def infer_roster(lines):
    names = set()
    for line in lines:
        match = DIALOGUE_RE.match(line)
        if match:
            names.update(split_names(match.group("audience")))
    if not names:
        raise ValueError("Could not infer any character names from dialogue audiences.")
    return names


def route_lines(lines, roster):
    routed = {name: [] for name in roster}
    for line in lines:
        dialogue = DIALOGUE_RE.match(line)
        if dialogue:
            audience = split_names(dialogue.group("audience")) & roster
            direct_targets = audience | {
                dialogue.group("speaker"),
                dialogue.group("target"),
            }
            for name in direct_targets & roster:
                routed[name].append(line)

            meta = dialogue.group("meta")
            volume = meta.split(",", 1)[0].strip()
            if volume in SCREAM_VOLUMES:
                spoken_line = ACTION_PREFIX_RE.sub(
                    "",
                    dialogue.group("payload"),
                    count=1,
                )
                remote_line = (
                    f"[{dialogue.group('time')}] {dialogue.group('label')} "
                    f"({overheard_table_label(dialogue.group('label'), dialogue.group('table'))}) "
                    f"{dialogue.group('speaker')} -> {dialogue.group('target')} "
                    f"[{volume}]: {spoken_line} | "
                    f"{dialogue.group('audience_label')}=[{dialogue.group('audience')}]"
                )
                for name in roster - audience:
                    routed[name].append(remote_line)
            continue

        event = EVENT_RE.match(line)
        if event:
            targets = {
                event.group("speaker"),
                event.group("target"),
            }
            targets.update(split_names(event.group("keywords") or ""))
            for name in targets & roster:
                routed[name].append(line)
    return routed


def rebuild(detailed_log, output_dir):
    lines = detailed_log.read_text(encoding="utf-8").splitlines()
    roster = infer_roster(lines)
    routed = route_lines(lines, roster)
    filenames = unique_filename_map(roster)

    backup_dir = None
    if output_dir.exists():
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_dir = output_dir.with_name(
            f"{output_dir.name}.pre_rebuild_{timestamp}"
        )
        counter = 2
        while backup_dir.exists():
            backup_dir = output_dir.with_name(
                f"{output_dir.name}.pre_rebuild_{timestamp}_{counter}"
            )
            counter += 1
        output_dir.rename(backup_dir)

    output_dir.mkdir(parents=True)
    for name in sorted(roster):
        path = output_dir / f"{filenames[name]}.log"
        content = "\n".join(routed[name])
        path.write_text(content + ("\n" if content else ""), encoding="utf-8")
    return roster, routed, backup_dir


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("detailed_log", type=Path)
    parser.add_argument(
        "--output-dir",
        type=Path,
        help="Defaults to <detailed-log-directory>/characters",
    )
    args = parser.parse_args()
    detailed_log = args.detailed_log.resolve()
    output_dir = (
        args.output_dir.resolve()
        if args.output_dir
        else detailed_log.parent / "characters"
    )
    roster, routed, backup_dir = rebuild(detailed_log, output_dir)
    print(f"Rebuilt {len(roster)} character logs in {output_dir}")
    print(f"Total routed lines: {sum(len(lines) for lines in routed.values())}")
    if backup_dir:
        print(f"Previous character logs moved to {backup_dir}")


if __name__ == "__main__":
    main()
