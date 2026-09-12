#!/usr/bin/env python3
"""Stop hook: block stopping if the last assistant message used an em dash."""

import json
import sys

EM_DASH = "—"


def last_assistant_text(transcript_path: str) -> str:
    """Return the text of the most recent assistant message in the transcript."""
    texts = []
    try:
        with open(transcript_path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return ""

    for line in reversed(lines):
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        for block in entry.get("message", {}).get("content", []) or []:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block.get("text", ""))
        break

    return "\n".join(texts)


def main() -> None:
    """Block the Stop event if the last assistant message contains an em dash."""
    data = json.load(sys.stdin)
    transcript_path = data.get("transcript_path")

    if not transcript_path:
        print("{}")
        return

    text = last_assistant_text(transcript_path)

    if EM_DASH in text:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": (
                        "Your last response contained an em dash (—). "
                        "CLAUDE.md forbids em dashes, rewrite that response "
                        "without using one."
                    ),
                }
            )
        )
    else:
        print("{}")


if __name__ == "__main__":
    main()
