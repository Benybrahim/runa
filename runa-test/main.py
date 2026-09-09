"""main.py: the application entry point.

Loads `.env` so every `runa` command (and this file, run directly) picks up
whichever API key(s) the agents below need, without exporting anything into
the shell. There's no separate configuration step beyond that: a model is a
per-`Agent` class attribute (see `app/agents/`), and Runa resolves it to the
right provider (OpenAI, Anthropic, Google, Meta, DeepSeek, or Alibaba) from
its name, so nothing here wires up a model or provider globally.
"""

from dotenv import load_dotenv

load_dotenv()


if __name__ == "__main__":
    # from app.agents.example_agent import ExampleAgent
    #
    # print(ExampleAgent().run_sync("...").output)
    pass
