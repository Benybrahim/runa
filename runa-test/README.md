# runa-test

A Runa application.

## Layout

- `main.py`: application entry point, loads `.env`
- `.env`: your model's API key, gitignored; fill it in before running
- `app/agents/`: Agent subclasses
- `app/tools/`: `@tool`-decorated functions
- `app/prompts/`: prompt text, kept out of Python source
- `app/evaluations/`: eval cases, run with `runa eval`
- `tests/`: deterministic tests, run with `runa test`
- `config/`: shared config (clients, settings)
- `db/runa.db`: conversation history and traces, see `runa chat --list`/`--show`; don't commit it

Generate scaffolding with:

    runa generate agent MyAgent
    runa generate tool MyTool
    runa generate prompt MyAgent
    runa generate evaluation MyAgent
