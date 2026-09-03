"""cli/_project.py: shared machinery for CLI commands that load a Runa app.

`runa eval` and `runa runs show` both need `main.py` imported (so
`configure()` runs, same as `python main.py` would) before they can do
anything — factored out so neither command duplicates the sys.path /
sys.modules bookkeeping.
"""

import importlib
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path


def _reset_project_modules() -> None:
    """Drop cached `main`/`app` modules from a previous project's import.

    Each call may target a different project root, but Python caches
    imports by name in `sys.modules` — without this, a later call in the
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
        importlib.import_module("main")
        yield
    finally:
        sys.path.remove(root_str)
