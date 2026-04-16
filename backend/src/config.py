"""
Módulo de configuración del sistema.

Carga y valida la configuración desde variables de entorno,
con valores por defecto sensatos.

Phase 1: field definitions live in cohesive Pydantic mixins under
``src.env_settings.grouped_settings``; :class:`AppSettings` composes them. ``Settings`` remains a
backward-compatible alias for ``AppSettings``.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from src.env_settings.grouped_settings import (
    ApiRuntimeSettings,
    ArtifactStorageSettings,
    AuthSettings,
    ConsolidationSettings,
    DatabasePersistenceSettings,
    DebugRuntimeSettings,
    EvidenceSettings,
    LimitsAndSchemaSettings,
    LlmProviderSettings,
    PathsOutputSettings,
    PhotosInputSettings,
    PipelineVisionSettings,
)
from src.env_settings.sqlserver_resolution import (
    SqlServerConfigurationError,
    SqlServerConnectionResolution,
    odbc_connection_string_server_keyword_value,
    remap_sqlserver_connection_string_server_if_needed,
    remap_sqlserver_server_for_container_if_needed,
    resolve_sqlserver_connection_config,
    resolve_sqlserver_effective_connection_string,
    sqlserver_configuration_error_message,
)

# backend/src/config.py -> parents[1] == backend/, parents[2] == repo root
_CONFIG_FILE = Path(__file__).resolve()
_BACKEND_ROOT = _CONFIG_FILE.parents[1]
_REPO_ROOT = _CONFIG_FILE.parents[2]


def _load_dotenv_files(*, for_reload: bool = False) -> None:
    """Load `.env` from repo root and `backend/` so vars match `dev.sh` / root `.env` when cwd is `backend/`.

    Initial load: repo root does not override existing OS env (exported vars win). `backend/.env` can
    override keys from repo for local developer overrides. Cwd `.env` fills remaining gaps.

    Reload: file values override OS env so edits to `.env` take effect after `reload_settings()`.
    """
    override_repo = for_reload
    repo_env = _REPO_ROOT / ".env"
    if repo_env.is_file():
        load_dotenv(repo_env, override=override_repo)
    backend_env = _BACKEND_ROOT / ".env"
    if backend_env.is_file():
        load_dotenv(backend_env, override=True)
    load_dotenv(override=for_reload)


# Cargar variables de entorno desde .env (raíz del repo + backend + cwd)
_load_dotenv_files(for_reload=False)


class AppSettings(
    LlmProviderSettings,
    PipelineVisionSettings,
    PathsOutputSettings,
    ApiRuntimeSettings,
    ArtifactStorageSettings,
    LimitsAndSchemaSettings,
    PhotosInputSettings,
    DatabasePersistenceSettings,
    DebugRuntimeSettings,
    AuthSettings,
    EvidenceSettings,
    ConsolidationSettings,
):
    """Top-level application settings — composed groups (field validators live on group mixins)."""

    model_config = {"extra": "forbid"}

    @property
    def sqlserver_effective_connection_string(self) -> str:
        """Canonical ODBC connection string (``SQLSERVER_CONNECTION_STRING`` or built from split vars)."""
        return (self.sqlserver_connection_string or "").strip()

    def require_sqlserver_connection_string(self) -> str:
        """Return a non-empty ODBC connection string or raise :class:`SqlServerConfigurationError`."""
        r = resolve_sqlserver_connection_config()
        if r.connection_string.strip():
            return r.connection_string.strip()
        msg = sqlserver_configuration_error_message(r)
        raise SqlServerConfigurationError(
            msg,
            missing_env_vars=r.missing_env_vars,
            config_mode=r.mode,
        )

    def ensure_output_dir(self) -> Path:
        """Asegura que el directorio de salida existe y lo crea si es necesario.

        Returns:
            Path al directorio de salida.
        """
        output_path = Path(self.output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        return output_path


# Historical type name — identical to AppSettings (flat field access preserved).
Settings = AppSettings

_settings: Optional[AppSettings] = None


def load_settings() -> AppSettings:
    """Carga la configuración desde variables de entorno.

    La configuración se carga una vez y se cachea. Si necesitas
    recargar la configuración (por ejemplo, después de cambiar .env),
    usa reload_settings().

    Returns:
        AppSettings: Instancia de configuración.
    """
    global _settings
    if _settings is None:
        _settings = AppSettings()
    return _settings


def reload_settings() -> AppSettings:
    """Recarga la configuración desde variables de entorno.

    Útil cuando se cambia el archivo .env en tiempo de ejecución.

    Returns:
        AppSettings: Nueva instancia de configuración.
    """
    global _settings
    _load_dotenv_files(for_reload=True)
    _settings = AppSettings()
    return _settings


def get_settings() -> AppSettings:
    """Obtiene la configuración actual (alias de load_settings para claridad).

    Returns:
        AppSettings: Instancia de configuración.
    """
    return load_settings()
