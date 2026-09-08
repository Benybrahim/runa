"""cli/_project.py: shared machinery for CLI commands that load a Runa app.

`run`, `eval`, and `test` all need `root/main.py` imported (so its
`load_dotenv()`, or whatever else it does, runs, same as `python main.py`
would) before they can do anything; factored out so no command duplicates
the sys.path / sys.modules bookkeeping.
"""

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class NotARunaProject(Exception):
    """Raised when a command needs an `app/` subdirectory `root` doesn't have.

    Shared across `generate.py`, `run.py`, `eval.py`, and `test.py` so `cli/main.py` can catch
    it once, regardless of which command's directory check failed.
    """


class AppLoadError(Exception):
    """Raised when importing `root/main.py` raises, for any reason.

    A generated `main.py` typically does nothing but `load_dotenv()`, so this is most often a
    missing `.env` or a bug in the developer's own `main.py`/`app/` code, not a Runa bug.
    `cli/main.py` catches this and prints one clean line instead of a raw multi-frame traceback,
    and points at `python main.py` for the full one, since that traceback belongs to the
    developer's own entry point.
    """


def _reset_project_modules() -> None:
    """Drop cached `main`/`app` modules from a previous project's import.

    Each call may target a different project root, but Python caches imports by name in
    `sys.modules`; without this, a later call in the same process (e.g. across tests) would
    silently reuse a previous project's `main`/`app` instead of the one at `root`.
    """
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            del sys.modules[name]


@contextmanager
def loaded_app(root: Path) -> Iterator[None]:
    """Import `root/main.py` for the block, then remove `root` from `sys.path`."""
    root_str = str(root)
    _reset_project_modules()
    sys.path.insert(0, root_str)
    try:
        try:
            importlib.import_module("main")
        except ModuleNotFoundError as exc:
            if exc.name == "main":
                raise  # cli/main.py already gives this its own clean message
            raise AppLoadError(str(exc)) from exc
        except Exception as exc:
            raise AppLoadError(str(exc)) from exc
        yield
    finally:
        sys.path.remove(root_str)
