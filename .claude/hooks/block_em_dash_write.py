#!/usr/bin/env python3
"""PreToolUse hook: deny Write/Edit calls whose content contains an em dash."""

import json
import sys

EM_DASH = "—"


def main() -> None:
    """Deny the PreToolUse event if the write content contains an em dash."""
    data = json.load(sys.stdin)
    tool_input = data.get("tool_input", {})
    text = tool_input.get("content") or tool_input.get("new_string") or ""

    if EM_DASH in text:
        print(
            json.dumps(
                {
                    "hookSpecificOutput": {
                        "hookEventName": "PreToolUse",
                        "permissionDecision": "deny",
                        "permissionDecisionReason": (
                            "Em dash (—) detected. CLAUDE.md forbids em dashes "
                            "in this project, rewrite using a comma, period, or "
                            "parentheses instead."
                        ),
                    }
                }
            )
        )
    else:
        print("{}")


if __name__ == "__main__":
    main()
