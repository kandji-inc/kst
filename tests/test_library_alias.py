"""Smoke tests for the kst → iructl alias mechanism."""

import sys
import types

import pytest

import kst  # noqa: F401  — bootstrap iructl identity before any test runs


def test_top_level_app_import() -> None:
    import iructl

    import kst

    assert kst.app is iructl.app


def test_submodule_aliasing() -> None:
    import iructl.api.client
    from kst.api import client

    assert client is iructl.api.client


def test_legacy_import_paths_work() -> None:
    from kst.exceptions import GitRepositoryError  # noqa: F401


def test_kst_error_alias() -> None:
    from kst.exceptions import IructlError, KstError

    assert KstError is IructlError


def test_import_order_enforced(monkeypatch: pytest.MonkeyPatch) -> None:
    """If iructl loads first, the wrapper bootstrap can't apply — raise."""
    # Wipe both modules from sys.modules so the next import re-runs __init__.
    monkeypatch.delitem(sys.modules, "kst", raising=False)
    monkeypatch.delitem(sys.modules, "iructl", raising=False)
    # Plant a stub iructl so the guard sees it.
    monkeypatch.setitem(sys.modules, "iructl", types.ModuleType("iructl"))
    with pytest.raises(ImportError, match="kst must be imported before iructl"):
        import kst  # noqa: F401
