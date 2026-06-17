"""Parametrized lock on legacy kst's public API surface."""

import importlib

import pytest

import kst  # noqa: F401  — bootstrap iructl identity before any test runs

LEGACY_KST_PUBLIC_API: dict[str, frozenset[str]] = {
    "kst": frozenset({"app", "main"}),
    "kst.api": frozenset(
        {
            "ApiClient",
            "ApiConfig",
            "ApiPayloadType",
            "CustomAppPayload",
            "CustomAppUploadPayload",
            "CustomAppsResource",
            "CustomProfilePayload",
            "CustomProfilesResource",
            "CustomScriptPayload",
            "CustomScriptsResource",
            "ExecutionFrequency",
            "InstallEnforcement",
            "InstallType",
            "PayloadList",
            "SelfServiceCategoriesResource",
            "SelfServiceCategoryPayload",
        }
    ),
    "kst.exceptions": frozenset(
        {
            "ApiClientError",
            "DuplicateInfoFileError",
            "DuplicateProfileError",
            "DuplicateScriptError",
            "GitRepositoryError",
            "InvalidInfoFileError",
            "InvalidProfileError",
            "InvalidRepositoryError",
            "InvalidRepositoryMemberError",
            "InvalidScriptError",
            "KstError",
            "MissingInfoFileError",
            "MissingProfileError",
            "MissingScriptError",
        }
    ),
    "kst.repository": frozenset(
        {
            "ACCEPTED_INFO_EXTENSIONS",
            "CustomProfile",
            "CustomScript",
            "ExecutionFrequency",
            "File",
            "InfoFile",
            "InfoFormat",
            "MemberBase",
            "Mobileconfig",
            "PROFILE_INFO_HASH_KEYS",
            "PROFILE_RUNS_ON_PARAMS",
            "ProfileInfoFile",
            "Repository",
            "RepositoryDirectory",
            "SCRIPT_INFO_HASH_KEYS",
            "SUFFIX_MAP",
            "Script",
            "ScriptInfoFile",
        }
    ),
}


@pytest.mark.parametrize(
    ("module_path", "symbol"),
    [
        (module, sym)
        for module, syms in LEGACY_KST_PUBLIC_API.items()
        for sym in sorted(syms)
    ],
)
def test_legacy_symbol_resolves(module_path: str, symbol: str) -> None:
    module = importlib.import_module(module_path)
    assert hasattr(module, symbol), (
        f"{module_path}.{symbol} no longer resolves through the kst wrapper. "
        "Either iructl removed/renamed it (add a back-compat alias in "
        "kst/__init__.py) or this is a deliberate API break (update "
        "LEGACY_KST_PUBLIC_API)."
    )


def test_legacy_module_surface_resolves() -> None:
    """Every module legacy kst exposed still resolves under kst.*.

    The wrapper skips missing iructl modules silently at import; this fails
    loudly so we catch when iructl drops a path kst still promises.
    """
    from kst import _LEGACY_MODULES

    for rel in sorted(_LEGACY_MODULES):
        importlib.import_module(f"kst.{rel}")  # raises if not aliased / missing


def test_legacy_symbol_renames_resolve() -> None:
    """Every renamed legacy symbol still resolves to its iructl target.

    Fails loudly if iructl drops or re-renames a symbol kst still promises.
    """
    from kst import _LEGACY_SYMBOL_RENAMES

    for rel, renames in _LEGACY_SYMBOL_RENAMES.items():
        mod = importlib.import_module(f"kst.{rel}")
        for old, new in renames.items():
            assert hasattr(mod, new), (
                f"iructl.{rel}.{new} is missing; the legacy kst.{rel}.{old} "
                f"alias can no longer resolve. Update _LEGACY_SYMBOL_RENAMES."
            )
            assert getattr(mod, old) is getattr(mod, new)
