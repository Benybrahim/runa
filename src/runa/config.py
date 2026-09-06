"""config.py: backward-compatible facade over runa.application.

The app-wide Provider/RunStore used to live here as bare module globals.
They now live on `runa.application.application`, a real `Application`
instance, so an app can construct additional, isolated `Application`s
instead of being limited to one process-wide set of infrastructure (see
application.py). This module re-exports that instance and its exceptions,
and keeps the old free-function names working for existing imports. Prefer
`runa.application` directly in new code.
"""

from runa.application import (
    Application,
    Config,
    InvalidConfiguration,
    ProviderNotConfigured,
    application,
    configure,
)
from runa.persistence.store import RunStore
from runa.runtime.provider import Provider

__all__ = [
    "Application",
    "Config",
    "InvalidConfiguration",
    "ProviderNotConfigured",
    "application",
    "configure",
    "default_provider",
    "default_run_store",
]


def default_provider() -> Provider:
    return application.provider


def default_run_store() -> RunStore:
    return application.run_store
