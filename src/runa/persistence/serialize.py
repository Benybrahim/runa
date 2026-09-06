"""Explicit Run/Conversation <-> JSON conversion, for store backends that
need bytes.

Not a generic `dataclasses.asdict`/`**data` round-trip: a `ToolCall` is
shared by identity between `Run.tool_calls` and the assistant `Message`
that produced it: `approve()`/`deny()` mutate the copy in `Run.tool_calls`
and rely on the same object showing up in the message the Strategy inspects
next. That needs explicit handling a generic round-trip can't recover.

Artifact is open-ended: RUNA core defines `Artifact`, `TextArtifact`,
`DataArtifact`, `FileArtifact`, but applications are expected to subclass
`Artifact` directly for their own domain output (see `core/artifact.py`),
so this module can't hold a closed registry of known types. Each artifact
is tagged with `Artifact.artifact_type()`, its *durable* identity, which by
default is a dotted `module.ClassName` path but need not be: an
application can override it to decouple the tag from wherever the class
currently lives (see `core/artifact.py`'s docstring). Resolving a tag back
to a class is a two-step lookup (`_resolve_artifact_class` below): an
optional, entirely application-owned `artifact_resolver` mapping first, then a
`module.ClassName` import as the zero-config fallback. RUNA never
populates that mapping itself.

That import fallback trusts the store's contents enough to import a name
from it, the same trust a `RunStore`'s caller already places in whatever
wrote it; this is a convenience for a store under the application's own
control, not a hardened interchange format. A store that may hold artifact
data from outside that control should pass an explicit `artifact_resolver`
mapping (e.g. via `SQLiteRunStore(path, artifact_resolver=...)`) and not rely
on the import fallback at all.

`Conversation` has neither concern; its messages aren't examined for
identity the way a Run's are, and it never holds Artifacts directly, so its
(de)serialization is a plain nested walk that reuses
`_tool_call_to_dict`/`_tool_call_from_dict` below.
"""

import importlib
import json
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from runa.core import (
    Artifact,
    Conversation,
    EffectStatus,
    Event,
    EventType,
    Message,
    Role,
    Run,
    RunStatus,
    ToolCall,
)
from runa.core.state import ConversationState, RunState


def _artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    data = dict(vars(artifact))
    data["created_at"] = artifact.created_at.isoformat()
    data["type"] = artifact.artifact_type()
    return data


def _resolve_artifact_class(
    type_tag: str, artifact_resolver: Mapping[str, type[Artifact]] | None
) -> type[Artifact]:
    if artifact_resolver is not None and type_tag in artifact_resolver:
        return artifact_resolver[type_tag]
    module_name, _, class_name = type_tag.rpartition(".")
    try:
        if not module_name:
            raise ImportError("not a 'module.ClassName' path")
        return getattr(importlib.import_module(module_name), class_name)
    except (ImportError, AttributeError) as exc:
        raise LookupError(
            f"cannot resolve artifact type {type_tag!r}: not found in the "
            "supplied artifact_resolver mapping, and it isn't an importable "
            "'module.ClassName' path either"
        ) from exc


def _artifact_from_dict(
    data: dict[str, Any],
    artifact_resolver: Mapping[str, type[Artifact]] | None = None,
) -> Artifact:
    data = dict(data)
    cls = _resolve_artifact_class(data.pop("type"), artifact_resolver)
    data["created_at"] = datetime.fromisoformat(data["created_at"])
    return cls(**data)


def _json_safe(value: Any) -> Any:
    """`value` unchanged if it's already JSON-safe, else its `str()`.

    A Tool's return value isn't constrained to be JSON-serializable (it may
    be an `Artifact` or any other plain Python object), but `ToolCall.result`
    holds whatever the Tool actually returned (application code inspects it
    directly, e.g. to get the real Artifact back), so it can't be coerced at
    the point of assignment. Persistence still needs *something* writable:
    falling back to `str(value)` matches what the model itself was already
    shown for this call (`content` in `Executor._call_tool`) rather than
    raising and losing the whole Run to one non-serializable result.

    `Run.input` and `Run.result` get the same treatment for the same reason:
    `Agent.run(input: Any, ...)` places no constraint on `input`, and
    architecture.md §2 explicitly expects `Result` to hold structured,
    application-defined objects, not just text; the Strategy's `Complete`
    action can carry any value as the Run's final result. A Run round-tripped
    through a store
    loses the original object's type either way once it isn't JSON-safe (a
    dataclass decoded back from JSON is a plain dict, not that dataclass);
    the choice here is only between that degraded-but-present `str()` form
    and losing the whole Run to a `save()` that raises: the latter is worse
    for a value the application may not control (e.g. `input` handed in by a
    caller) and, unlike a raise inside a request/response cycle, can fail
    silently when it happens on a background queue's worker thread.
    """
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _json_safe_dict(mapping: dict[str, Any]) -> dict[str, Any]:
    """`_json_safe` applied per value, for State, the other place the docs
    invite application code to put an arbitrary object (e.g.
    `run.state.findings`). One bad value falls back to its `str()`; the
    rest of the mapping still round-trips normally.
    """
    return {key: _json_safe(value) for key, value in mapping.items()}


def _tool_call_to_dict(tool_call: ToolCall) -> dict[str, Any]:
    return {
        "id": tool_call.id,
        "name": tool_call.name,
        "arguments": tool_call.arguments,
        "result": _json_safe(tool_call.result),
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
        "agent_name": run.agent_name,
        "agent_version": run.agent_version,
        "active_agent_name": run.active_agent_name,
        "active_agent_version": run.active_agent_version,
        "parent_run_id": run.parent_run_id,
        "conversation_id": run.conversation_id,
        "input": _json_safe(run.input),
        "state": _json_safe_dict(run.state),
        "messages": [
            {
                "id": message.id,
                "role": message.role.value,
                "content": message.content,
                "tool_call_ids": [tc.id for tc in message.tool_calls],
                "tool_call_id": message.tool_call_id,
                "usage": message.usage,
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
        "result": _json_safe(run.result),
        "error": run.error,
        "status": run.status.value,
        "created_at": run.created_at.isoformat(),
    }


def run_from_dict(
    data: dict[str, Any],
    *,
    artifact_resolver: Mapping[str, type[Artifact]] | None = None,
) -> Run:
    """Reconstruct a Run from a dict produced by `run_to_dict`.

    `artifact_resolver` maps a stored `Artifact.artifact_type()` tag to the
    class to reconstruct it as; an application supplies it when it isn't
    relying on the tag being an importable `module.ClassName` path (see the
    module docstring). Consulted before the import fallback, so it can also
    redirect a tag whose original class has since moved or been renamed.
    """
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
            usage=m.get("usage"),
        )
        for m in data["messages"]
    ]

    return Run(
        id=data["id"],
        agent_name=data["agent_name"],
        agent_version=data["agent_version"],
        active_agent_name=data["active_agent_name"],
        active_agent_version=data["active_agent_version"],
        parent_run_id=data["parent_run_id"],
        conversation_id=data["conversation_id"],
        input=data["input"],
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
        artifacts=[
            _artifact_from_dict(a, artifact_resolver) for a in data["artifacts"]
        ],
        result=data["result"],
        error=data["error"],
        status=RunStatus(data["status"]),
        created_at=datetime.fromisoformat(data["created_at"]),
    )


def run_to_json(run: Run) -> str:
    return json.dumps(run_to_dict(run))


def run_from_json(
    raw: str,
    *,
    artifact_resolver: Mapping[str, type[Artifact]] | None = None,
) -> Run:
    return run_from_dict(json.loads(raw), artifact_resolver=artifact_resolver)


def conversation_to_dict(conversation: Conversation) -> dict[str, Any]:
    """Convert a Conversation into a plain, JSON-serializable dict."""
    return {
        "id": conversation.id,
        "state": _json_safe_dict(conversation.state),
        "messages": [
            {
                "id": message.id,
                "role": message.role.value,
                "content": message.content,
                "tool_calls": [_tool_call_to_dict(tc) for tc in message.tool_calls],
                "tool_call_id": message.tool_call_id,
                "usage": message.usage,
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
                usage=m.get("usage"),
            )
            for m in data["messages"]
        ],
    )


def conversation_to_json(conversation: Conversation) -> str:
    return json.dumps(conversation_to_dict(conversation))


def conversation_from_json(raw: str) -> Conversation:
    return conversation_from_dict(json.loads(raw))
