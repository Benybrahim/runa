# Model Providers

`model` is a plain string on your `Agent`:

```python
class SupportAgent(Agent):
    name = "support_agent"
    model = "claude-sonnet-5"
```

No client to construct, no provider to configure globally — Runa resolves
the string to a provider by its prefix, and reads the matching API key
from the environment (typically via `.env`, loaded by your app's
`main.py`).

| Prefix     | Provider   | Env var             |
|------------|------------|----------------------|
| `claude`   | Anthropic  | `ANTHROPIC_API_KEY`  |
| `gpt`      | OpenAI     | `OPENAI_API_KEY`     |
| `gemini`   | Google     | `GEMINI_API_KEY`     |
| `llama`    | Meta       | `LLAMA_API_KEY`      |
| `deepseek` | DeepSeek   | `DEEPSEEK_API_KEY`   |
| `qwen`     | Alibaba    | `DASHSCOPE_API_KEY`  |

An unrecognized or bare model name falls back to the OpenAI-compatible
backend. The default, when `model` isn't set, is `"gpt-5.4-nano"`.

Every provider except Anthropic speaks the same chat-completions wire
format, so they share one backend; Anthropic's Messages API is shaped
differently and gets its own.

## Model Settings

Tune sampling per agent with `model_settings` — `ModelSettings` currently
lives at `runa._types` (not yet re-exported from `runa` itself):

```python
from runa import Agent
from runa._types import ModelSettings


class SupportAgent(Agent):
    name = "support_agent"
    model_settings = ModelSettings(temperature=0.2, max_tokens=500)
```

## Mixing Providers

Because `model` is per-agent, a single application can freely mix
providers across agents — a fast, cheap model for routing, a stronger one
for the agent that actually answers:

```python
class Router(Agent):
    name = "router"
    model = "gpt-5.4-nano"
    subagents = [SupportAgent.handoff]


class SupportAgent(Agent):
    name = "support_agent"
    model = "claude-opus-5"
```
