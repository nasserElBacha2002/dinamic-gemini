from dataclasses import dataclass

from src.config import Settings, load_settings


@dataclass(frozen=True)
class AuthSettings:
    """
    Auth-related configuration values for v3.2.1 minimal administrative authentication.

    This is a thin projection over the global Settings model so the auth layer
    has a focused view of the fields it needs. Phase 1 only defines structure;
    enforcement and validation happen in later phases.

    ``jairo_password_hash``: optional temporary second operator; empty string means disabled.
    Jairo login is only evaluated when the primary admin credential pair is configured.

    ``admin_client_id`` / ``jairo_client_id``: optional Observability company scope embedded in JWT.
    Empty means platform-unbound principal (legacy single-tenant behavior).
    """

    admin_username: str
    admin_password_hash: str
    jairo_password_hash: str
    token_secret: str
    token_expires_minutes: int
    refresh_token_expires_minutes: int
    admin_client_id: str = ""
    jairo_client_id: str = ""


def get_auth_settings(settings: Settings | None = None) -> AuthSettings:
    """
    Return auth settings snapshot based on global Settings.

    Jairo (``jairo_password_hash``) is optional; empty means disabled and requires
    a configured primary admin pair (see ``authenticate_admin`` in ``auth.service``).
    """

    s = settings or load_settings()
    return AuthSettings(
        admin_username=s.admin_username,
        admin_password_hash=s.admin_password_hash,
        jairo_password_hash=s.auth_jairo_password_hash,
        token_secret=s.auth_token_secret,
        token_expires_minutes=s.auth_token_expires_minutes,
        refresh_token_expires_minutes=s.auth_refresh_token_expires_minutes,
        admin_client_id=(getattr(s, "auth_admin_client_id", "") or "").strip(),
        jairo_client_id=(getattr(s, "auth_jairo_client_id", "") or "").strip(),
    )
