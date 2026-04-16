"""Composition root: container creation and parity with v3_deps entrypoints."""

from __future__ import annotations

from pathlib import Path

import pytest

import src.config as config_module
from src.api import dependencies as deps
from src.config import AppSettings, Settings, load_settings
from src.runtime.app_container import AppContainer, get_app_container, reset_app_container_for_tests
from src.runtime.v3_deps import get_aisle_repo, get_artifact_store, get_inventory_repo, get_job_repo


@pytest.fixture(autouse=True)
def _reset_container_and_settings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    reset_app_container_for_tests()
    config_module._settings = None
    yield
    reset_app_container_for_tests()
    config_module._settings = None


def test_app_settings_is_settings_alias() -> None:
    assert Settings is AppSettings


def test_container_builds_from_explicit_settings() -> None:
    s = AppSettings()
    c = AppContainer(s)
    assert c.settings is s
    inv = c.get_inventory_repo()
    assert inv is c.get_inventory_repo()


def test_settings_groups_env_database_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SQLSERVER_ENABLED", "false")
    config_module._settings = None
    reset_app_container_for_tests()
    s = load_settings()
    assert s.sqlserver_enabled is False


def test_artifact_storage_single_instance_across_api_v3deps_container(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """API ``get_artifact_storage``, ``v3_deps.get_artifact_store``, and the container must share one adapter."""
    out = str(tmp_path / "artifact_wiring_out")
    monkeypatch.setenv("ARTIFACT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("OUTPUT_DIR", out)
    config_module._settings = None
    reset_app_container_for_tests()

    c = get_app_container()
    a = deps.get_artifact_storage()
    b = c.get_artifact_storage()
    d = get_artifact_store()
    assert a is b is d


def test_v3_deps_repo_getters_delegate_to_same_container_instances() -> None:
    c = get_app_container()
    assert get_inventory_repo() is c.get_inventory_repo()
    assert get_job_repo() is c.get_job_repo()
    assert get_aisle_repo() is c.get_aisle_repo()
