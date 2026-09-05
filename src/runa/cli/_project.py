"""cli/_project.py: shared machinery for CLI commands that load a Runa app.

`runa eval` and `runa runs show` both need `main.py` imported (so
`configure()` runs, same as `python main.py` would) before they can do
anything, factored out so neither command duplicates the sys.path /
sys.modules bookkeeping.
"""

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


class AppLoadError(Exception):
    """Raised when importing root/main.py raises, for any reason.

    The most common cause early in a project's life is a Provider (e.g.
    `OpenAIProvider()`) failing fast in `__init__` because no API key is set
    yet (architecture.md: "explicit beats implicit"; `main.py`'s
    `configure()` call constructs its Provider eagerly, on purpose). Without
    this wrapper, that surfaces as a raw multi-frame traceback through
    contextlib/importlib/the vendor SDK for every command that loads the app,
    including `runs list`/`show`/`pending`, which never touch the Provider
    at all. `cli/main.py` catches this and prints one clean line instead,
    the same "operator-input error, not a Runa bug" treatment `main()`
    already gives a missing `main.py`, and points at `python main.py` for
    the full traceback, since that's a real bug in the developer's own
    entry point and deserves to be seen in full there.

    Deliberately generic rather than matching specific vendor exception
    types (`openai.OpenAIError` and friends): cli/ has no business knowing
    about provider internals (architecture.md §5: "provider-specific
    concepts must remain inside provider adapters").
    """


def _reset_project_modules() -> None:
    """Drop cached `main`/`app` modules from a previous project's import.

    Each call may target a different project root, but Python caches
    imports by name in `sys.modules`; without this, a later call in the
    same process (e.g. across tests) would silently reuse a previous
    project's `main`/`app` instead of the one at `root`.
    """
    for name in list(sys.modules):
        if name == "main" or name == "app" or name.startswith("app."):
            del sys.modules[name]


@contextmanager
def loaded_app(root: Path) -> Iterator[None]:
    """Import `root/main.py`, triggering its `configure()` call, for the block."""
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
