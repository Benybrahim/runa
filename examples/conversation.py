"""conversation.py: carry history across multiple Runs.

A `Conversation` is separate from a `Run`: it survives across Runs while
each Run stays a single execution. Pass the same `Conversation` into
successive `Agent.run()` calls and each one sees the prior turns, without
the caller re-assembling message history by hand.

Requires OPENAI_API_KEY in the environment.
Run with: uv run python examples/conversation.py
"""

from runa import Agent, Conversation, OpenAIProvider, configure


class SupportAgent(Agent):
    instructions = "Help customers with their orders. Be concise."


if __name__ == "__main__":
    configure(provider=OpenAIProvider())

    conversation = Conversation()

    first = SupportAgent.run(
        "My order #A123 hasn't arrived.", conversation=conversation
    )
    print(first.result)

    second = SupportAgent.run(
        "What was that order number again?", conversation=conversation
    )
    print(second.result)
