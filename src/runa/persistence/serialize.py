"""Explicit Run/Conversation <-> JSON conversion, for store backends that
need bytes.

Not a generic `dataclasses.asdict`/`**data` round-trip: Artifact is
polymorphic (five concrete subclasses), and a `ToolCall` is shared by
identity between `Run.tool_calls` and the assistant `Message` that produced
it — `approve()`/`deny()` mutate the copy in `Run.tool_calls` and rely on
the same object showing up in the message the Strategy inspects next. Both
of those need explicit handling that a generic round-trip can't recover.

`Conversation` has neither concern — its messages aren't examined for
identity the way a Run's are — so its (de)serialization is a plain nested
walk that reuses `_tool_call_to_dict`/`_tool_call_from_dict` below.
"""

import json
from datetime import datetime
from typing import Any

from runa.core import (
    ActionArtifact,
    Artifact,
    CitationSetArtifact,
    Conversation,
    DataArtifact,
    EffectStatus,
    Event,
    EventType,
    FileArtifact,
    Message,
    PlanArtifact,
    Role,
    Run,
    RunStatus,
    TextArtifact,
    ToolCall,
)
from runa.core.state import ConversationState, RunState

_ARTIFACT_TYPES: dict[str, type[Artifact]] = {
    "text": TextArtifact,
    "data": DataArtifact,
    "file": FileArtifact,
    "citation_set": CitationSetArtifact,
    "plan": PlanArtifact,
    "action": ActionArtifact,
}


def _artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    for kind, cls in _ARTIFACT_TYPES.items():
        if type(artifact) is cls:
            data = dict(vars(artifact))
            data["created_at"] = artifact.created_at.isoformat()
            data["kind"] = kind
            return data
    raise TypeError(f"unknown artifact type: {type(artifact)!r}")


def _artifact_from_dict(data: dict[str, Any]) -> Artifact:
    data = dict(data)
    cls = _ARTIFACT_TYPES[data.pop("kind")]
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return cls(**data)


def _tool_call_to_dict(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
        "result": tool_call.result,
        "approved": tool_call.approved,
        "error": tool_call.error,
        "attempts": tool_call.attempts,
        "idempotent": tool_call.idempotent,
        "effect": tool_call.effect.value,
    }


def _tool_call_from_dict(data: dict[str, Any]) -> ToolCall:
    return ToolCall(**{**data, "effect": EffectStatus(data["effect"])})


def run_to_dict(run: Run) -> dict[str, Any]:
    """Convert a Run into a plain, JSON-serializable dict."""
    tool_calls_by_id = {tc.id: _tool_call_to_dict(tc) for tc in run.tool_calls}

    return {
        "id": run.id,
        "agent_id": run.agent_id,
        "agent_version": run.agent_version,
        "input": run.input,
        "context": run.context,
        "state": dict(run.state),
        "messages": [
            {
                "id": message.id,
                "role": message.role.value,
                "content": message.content,
                "tool_call_ids": [tc.id for tc in message.tool_calls],
                "tool_call_id": message.tool_call_id,
            }
            for message in run.messages
        ],
        "events": [
            {
                "id": event.id,
                "type": event.type.value,
                "data": event.data,
                "timestamp": event.timestamp.isoformat(),
            }
            for event in run.events
        ],
        "tool_calls": tool_calls_by_id,
        "artifacts": [_artifact_to_dict(a) for a in run.artifacts],
        "result": run.result,
        "status": run.status.value,
        "created_at": run.created_at.isoformat(),
    }


def run_from_dict(data: dict[str, Any]) -> Run:
    """Reconstruct a Run from a dict produced by `run_to_dict`."""
    tool_calls_by_id = {
        tc_id: _tool_call_from_dict(tc) for tc_id, tc in data["tool_calls"].items()
    }

    messages = [
        Message(
            id=m["id"],
            role=Role(m["role"]),
            content=m["content"],
            tool_calls=[tool_calls_by_id[tc_id] for tc_id in m["tool_call_ids"]],
            tool_call_id=m["tool_call_id"],
        )
        for m in data["messages"]
    ]

    return Run(
        id=data["id"],
        agent_id=data["agent_id"],
        agent_version=data["agent_version"],
        input=data["input"],
        context=data["context"],
        state=RunState(data["state"]),
        messages=messages,
        events=[
            Event(
                id=e["id"],
                type=EventType(e["type"]),
                data=e["data"],
                timestamp=datetime.fromisoformat(e["timestamp"]),
            )
            for e in data["events"]
        ],
        tool_calls=list(tool_calls_by_id.values()),
        artifacts=[_artifact_from_dict(a) for a in data["artifacts"]],
        result=data["result"],
        status=RunStatus(data["status"]),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def run_to_json(run: Run) -> str:
    return json.dumps(run_to_dict(run))


def run_from_json(raw: str) -> Run:
    return run_from_dict(json.loads(raw))


def conversation_to_dict(conversation: Conversation) -> dict[str, Any]:
    """Convert a Conversation into a plain, JSON-serializable dict."""
    return {
        "id": conversation.id,
        "state": dict(conversation.state),
        "messages": [
            {
                "id": message.id,
                "role": message.role.value,
                "content": message.content,
                "tool_calls": [_tool_call_to_dict(tc) for tc in message.tool_calls],
                "tool_call_id": message.tool_call_id,
            }
            for message in conversation.messages
        ],
    }


def conversation_from_dict(data: dict[str, Any]) -> Conversation:
    """Reconstruct a Conversation from a dict produced by `conversation_to_dict`."""
    return Conversation(
        id=data["id"],
        state=ConversationState(data["state"]),
        messages=[
            Message(
                id=m["id"],
                role=Role(m["role"]),
                content=m["content"],
                tool_calls=[_tool_call_from_dict(tc) for tc in m["tool_calls"]],
                tool_call_id=m["tool_call_id"],
            )
            for m in data["messages"]
        ],
    )


def conversation_to_json(conversation: Conversation) -> str:
    return json.dumps(conversation_to_dict(conversation))


def conversation_from_json(raw: str) -> Conversation:
    return conversation_from_dict(json.loads(raw))
