"""`runa.eval.storage`: persist `Report`s to `runa.db`."""

from runa.eval.storage.sqlite import save_report

__all__ = ["save_report"]
