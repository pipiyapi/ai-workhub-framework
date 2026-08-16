#!/usr/bin/env python3
"""Apply Codex-curated knowledge sections to generated video note drafts."""

from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
import sys
from pathlib import Path


def replace_section(text: str, heading: str, next_heading: str, content: str) -> str:
    pattern = re.compile(rf"(?ms)^{re.escape(heading)}\n.*?(?=^{re.escape(next_heading)}\n)")
    replacement = f"{heading}\n\n{content.strip()}\n\n"
    updated, count = pattern.subn(lambda _: replacement, text, count=1)
    if count != 1:
        raise RuntimeError(f"section not found: {heading}")
    return updated


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--content", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    entries = json.loads(args.content.read_text(encoding="utf-8"))
    updated = []
    for video_id, entry in entries.items():
        raw_dir = root / "vault" / "raw" / "video" / "douyin" / video_id
        manifest = json.loads((raw_dir / "manifest.json").read_text(encoding="utf-8"))
        note_path = root / manifest["note_path"]
        note = note_path.read_text(encoding="utf-8")
        note = re.sub(r"(?m)^# .+$", f"# {entry['title']}", note, count=1)
        points = "\n".join(f"- {point}" for point in entry["points"])
        saved = "\n".join(f"- {point}" for point in entry["saved"])
        note = replace_section(note, "## 内容摘要", "## 核心观点", entry["summary"])
        note = replace_section(note, "## 核心观点", "## 详细内容", points)
        note = replace_section(note, "## 详细内容", "## 值得保存的观点", entry["details"])
        note = replace_section(note, "## 值得保存的观点", "## 关键画面", saved)
        atomic_write(note_path, note)
        updated.append(str(note_path))
    print(json.dumps({"updated": len(updated), "notes": updated}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
