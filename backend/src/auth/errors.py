from __future__ import annotations

from dataclasses import dataclass

from src.auth.schemas import AuthError, AuthErrorResponse


@dataclass(frozen=True)
class AuthHttpError(Exception):
    """
    Auth-specific HTTP error used to return a stable AuthErrorResponse payload.

    We avoid raising FastAPI's HTTPException directly because its default handler
    wraps payloads under {"detail": ...}, which would break the declared auth
    error contract.
    """

    status_code: int
    error: AuthError

    def to_response_body(self) -> dict:
        return AuthErrorResponse(error=self.error).model_dump()

