# Human Approval

Some tool calls are sensitive enough that a person should sign off before
they run — deleting a record, sending an email, spending money. Gate a
tool with `needs_approval`:

```python
from runa import Agent, approval, tool


@approval
def large_refund(amount: float) -> bool:
    """Refunds of $50 or more need a human to sign off."""
    return amount >= 50


@tool(needs_approval=large_refund)
def issue_refund(amount: float) -> str:
    """Refund the customer."""
    ...
```

`@approval` wraps a predicate the same way `@guardrail` does: its
parameters are looked up by name from the tool call's parsed arguments;
name one `ctx` or `call_id` to receive the run context or call id
instead. `True` means what the parameter is called — this call **needs
approval** — the same sense as a guardrail's tripwire, just gated on a
person instead of enforced automatically (see below).

You can also pass `needs_approval=True` to always require approval, with
no predicate.

`runa chat` prompts interactively for any call that needs approval:

```
approve issue_refund({"amount": 120})? [y/N]
```

Rejecting a call skips the tool entirely; the model sees "rejected by the
operator" instead of a result.

## `needs_approval` vs. a guardrail

Both are `predicate(args) -> bool`, and a tripped guardrail and a
call that needs approval both start from the same `True`. What happens
next is different:

| | `guardrails=[fn]` (tool guardrail) | `needs_approval=fn` |
|---|---|---|
| who makes the final call | the predicate itself | a human, later |
| on `True` | raises a tripwire exception | pauses, returns an `Interruption` |
| run outcome | the run ends in an error | the run is resumable |
| can be overridden | no | yes — the operator can approve anyway |

Use a **guardrail** for calls that must never go through no matter who's
asking — the predicate is the whole decision. Use **`needs_approval`**
for calls that are fine *with a person's sign-off* — the predicate only
decides whether to stop and ask; the actual yes/no comes from whoever
resolves the pending call.
