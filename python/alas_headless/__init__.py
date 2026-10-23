"""Controller-side components for AzurLaneAutoScript Headless.

Runtime utilities can import their own modules without initializing the full
ALAS facade. Existing ``from alas_headless import ...`` calls retain the same
objects and exports.
"""

from importlib import import_module as _import_module
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ._public_api import *  # noqa: F403 - preserve static public API discovery


def __getattr__(name):
    if name.startswith("_") and name != "__all__":
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    api = _import_module("._public_api", __name__)
    try:
        value = getattr(api, name)
    except AttributeError:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from None
    globals()[name] = value
    return value


def __dir__():
    api = _import_module("._public_api", __name__)
    return sorted(set(globals()) | set(vars(api)))
