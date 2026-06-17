"""Deprecated kst package — thin compatibility wrapper around iructl.

This module sets the env vars iructl reads at import time so iructl runs with
kst-parity identity ("kst" prog_name, "KST_*" env prefix, "Kandji Sync Toolkit"
branding), then aliases the public iructl.* modules into the kst.* namespace so
legacy import paths like `from kst.api import client` continue to resolve.
"""

import importlib
import importlib.metadata
import os
import sys
import warnings


def _invoked_as_cli() -> bool:
    """True when the package is imported to run kst's own CLI."""
    if os.path.basename(sys.argv[0] if sys.argv else "") == "kst":
        return True  # `kst` console script
    after_m = (
        sys.orig_argv[sys.orig_argv.index("-m") + 1 :] if "-m" in sys.orig_argv else []
    )
    first = after_m[0] if after_m else ""
    return first == "kst" or first.startswith("kst.")  # `python -m kst[.submodule]`


def _alias_legacy_modules() -> None:
    """Alias the public iructl.* modules into the kst.* namespace."""
    for rel in sorted(_LEGACY_MODULES):
        try:
            mod = importlib.import_module(f"iructl.{rel}")
        except ImportError:
            continue  # module dropped from iructl; skip silently

        sys.modules[f"kst.{rel}"] = mod
        # Bind as an attribute of the parent package
        parent, _, child = f"kst.{rel}".rpartition(".")
        if (parent_mod := sys.modules.get(parent)) is not None:
            setattr(parent_mod, child, mod)


def _apply_symbol_renames() -> None:
    """Re-add renamed symbols onto the aliased modules so legacy names resolve."""
    for rel, renames in _LEGACY_SYMBOL_RENAMES.items():
        mod = sys.modules.get(f"kst.{rel}")
        if mod is None:
            continue  # module dropped from iructl; skip silently
        for old, new in renames.items():
            try:
                setattr(mod, old, getattr(mod, new))
            except AttributeError:
                continue  # iructl dropped the rename target; the contract
                # test (test_legacy_symbol_renames_resolve) flags it loudly


# Guard against late import
if "iructl" in sys.modules:
    raise ImportError(
        "kst must be imported before iructl. "
        "iructl was loaded with default branding ('Iru Control') before "
        "the kst wrapper could set its env vars. Move `import kst` "
        "above any iructl imports."
    )

os.environ["_IRUCTL_APP_NAME"] = "kst"
os.environ["_IRUCTL_APP_BRANDING"] = "Kandji Sync Toolkit"
os.environ["IRUCTL_ENV_PREFIX"] = "KST"

_LEGACY_MODULES = frozenset(
    {
        "api",
        "api.apps",
        "api.client",
        "api.payload",
        "api.profiles",
        "api.resource_base",
        "api.scripts",
        "api.self_service",
        "exceptions",
        "repository",
        "repository.content",
        "repository.custom_profile",
        "repository.custom_script",
        "repository.info",
        "repository.member_base",
        "repository.repository",
    }
)

_LEGACY_SYMBOL_RENAMES = {
    "exceptions": {"KstError": "IructlError"},
    "api": {"ApiPayloadType": "ApiPayload"},
}

# Load iructl now that its env vars are set, then alias the legacy modules.
import iructl  # noqa: E402, F401

_alias_legacy_modules()
_apply_symbol_renames()

# Re-export iructl's top-level surface under the kst namespace.
from iructl import *  # noqa: E402, F401, F403
from iructl import app  # noqa: E402, F401

__version__ = importlib.metadata.version("kst")

if not _invoked_as_cli():
    warnings.warn(
        "the kst package is deprecated; use iructl instead.",
        DeprecationWarning,
        stacklevel=2,
    )
