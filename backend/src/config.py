"""
Módulo de configuración del sistema.

Carga y valida la configuración desde variables de entorno,
con valores por defecto sensatos.

Phase 1: field definitions live in cohesive Pydantic mixins under
``src.env_settings.grouped_settings``; :class:`AppSettings` composes them. ``Settings`` remains a
backward-compatible alias for ``AppSettings``.
"""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv
from pydantic import model_validator
from typing_extensions import Self

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
    ObservabilitySettings,
    PathsOutputSettings,
    PhotosInputSettings,
    PipelineVisionSettings,
)
from src.env_settings.parsing import resolve_google_application_credentials_path
from src.env_settings.sqlserver_resolution import (
    SqlServerConfigurationError,
    resolve_sqlserver_connection_config,
    sqlserver_configuration_error_message,
)
from src.env_settings.sqlserver_resolution import (
    remap_sqlserver_connection_string_server_if_needed as remap_sqlserver_connection_string_server_if_needed,
)
from src.env_settings.sqlserver_resolution import (
    remap_sqlserver_server_for_container_if_needed as remap_sqlserver_server_for_container_if_needed,
)
from src.env_settings.sqlserver_resolution import (
    resolve_sqlserver_effective_connection_string as resolve_sqlserver_effective_connection_string,
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
    ObservabilitySettings,
):
    """Top-level application settings — composed groups (field validators live on group mixins)."""

    model_config = {"extra": "forbid"}

    @model_validator(mode="after")
    def validate_external_fallback_when_enabled(self) -> Self:
        """Fail closed at startup when per-image fallback is enabled but incomplete."""
        from src.application.services.image_processing.external_fallback_mode import (
            EXTERNAL_FALLBACK_MODE_PER_ASSET,
            parse_external_fallback_mode,
        )

        # Always validate mode (even when fallback disabled) — no silent defaults for junk.
        mode = parse_external_fallback_mode(
            getattr(self, "external_fallback_mode", None)
        )
        self.external_fallback_mode = mode

        if not bool(getattr(self, "external_fallback_per_image_enabled", False)):
            return self
        if mode == EXTERNAL_FALLBACK_MODE_PER_ASSET:
            import logging

            logging.getLogger(__name__).warning(
                "EXTERNAL_FALLBACK_MODE=PER_ASSET is deprecated; prefer GLOBAL_BATCH "
                "(temporary rollback only)."
            )
        provider = str(getattr(self, "external_fallback_provider", "") or "").strip().lower()
        model = str(getattr(self, "external_fallback_model", "") or "").strip()
        if not provider:
            raise ValueError(
                "EXTERNAL_FALLBACK_PROVIDER is required when "
                "EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=true"
            )
        if not model:
            raise ValueError(
                "EXTERNAL_FALLBACK_MODEL is required when "
                "EXTERNAL_FALLBACK_PER_IMAGE_ENABLED=true"
            )
        from src.pipeline.providers.definitions import (
            credential_configured,
            pipeline_provider_spec,
        )
        from src.pipeline.providers.registry import (
            UnknownPipelineProviderError,
            resolve_llm_executor,
        )

        try:
            resolve_llm_executor(provider, self)
        except UnknownPipelineProviderError as exc:
            raise ValueError(
                f"EXTERNAL_FALLBACK_PROVIDER={provider!r} is not a registered pipeline provider: {exc}"
            ) from exc
        spec = pipeline_provider_spec(provider)
        if spec is None:
            raise ValueError(
                f"EXTERNAL_FALLBACK_PROVIDER={provider!r} has no provider definition"
            )
        if not credential_configured(spec, self):
            raise ValueError(spec.credential_missing_message)
        return self

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


# ---------------------------------------------------------------------------
# Backward-compatible type alias (Phase 1 migration bridge)
#
# ``Settings`` is **not** a distinct model: it is the same class object as
# ``AppSettings``. Existing imports (`from src.config import Settings`) and
# annotations keep working while call sites migrate.
#
# **New code** should prefer ``AppSettings`` for clarity. This alias remains until
# a later phase retires it after bulk import updates.
# ---------------------------------------------------------------------------
Settings = AppSettings

_settings: AppSettings | None = None


def _normalize_gcp_credentials_settings(settings: AppSettings) -> AppSettings:
    """Map Docker ``/app/secrets/...`` paths to repo ``secrets/`` for local ``./dev.sh``."""
    raw = (settings.google_application_credentials or "").strip()
    if not raw:
        return settings
    resolved = resolve_google_application_credentials_path(raw)
    if resolved == raw:
        return settings
    return settings.model_copy(update={"google_application_credentials": resolved})


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
        _settings = _normalize_gcp_credentials_settings(AppSettings())
    return _settings


def reload_settings() -> AppSettings:
    """Recarga la configuración desde variables de entorno.

    Útil cuando se cambia el archivo .env en tiempo de ejecución.

    Returns:
        AppSettings: Nueva instancia de configuración.
    """
    global _settings
    _load_dotenv_files(for_reload=True)
    _settings = _normalize_gcp_credentials_settings(AppSettings())
    return _settings


def get_settings() -> AppSettings:
    """Obtiene la configuración actual (alias de load_settings para claridad).

    Returns:
        AppSettings: Instancia de configuración.
    """
    return load_settings()
