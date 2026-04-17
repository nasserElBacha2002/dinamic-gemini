from dataclasses import dataclass

from src.config import Settings, load_settings


@dataclass(frozen=True)
class AuthSettings:
    """
    Auth-related configuration values for v3.2.1 minimal administrative authentication.

    This is a thin projection over the global Settings model so the auth layer
    has a focused view of the fields it needs. Phase 1 only defines structure;
    enforcement and validation happen in later phases.
    """

    admin_username: str
    admin_password_hash: str
    jairo_password_hash: str
    token_secret: str
    token_expires_minutes: int
    refresh_token_expires_minutes: int


def get_auth_settings(settings: Settings | None = None) -> AuthSettings:
    """
    Return auth settings snapshot based on global Settings.

    In Phase 1 this does not enforce presence/validity; later phases should add
    stricter validation before enabling auth in non-dev environments.
    """

    s = settings or load_settings()
    return AuthSettings(
        admin_username=s.admin_username,
        admin_password_hash=s.admin_password_hash,
        jairo_password_hash=s.auth_jairo_password_hash,
        token_secret=s.auth_token_secret,
        token_expires_minutes=s.auth_token_expires_minutes,
        refresh_token_expires_minutes=s.auth_refresh_token_expires_minutes,
    )

