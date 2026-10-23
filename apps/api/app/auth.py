from __future__ import annotations

from dataclasses import dataclass

import httpx
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt

from app.config import settings

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Principal:
    subject: str


async def get_current_principal(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
) -> Principal:
    if settings.orion_auth_mode == "local":
        return Principal(subject="local-dev")
    if settings.orion_auth_mode != "clerk":
        raise HTTPException(status_code=503, detail="Authentication mode is not configured.")
    if not settings.clerk_issuer or not settings.clerk_jwks_url:
        raise HTTPException(status_code=503, detail="Clerk authentication is not configured.")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="A valid bearer token is required.",
        )
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            response = await client.get(settings.clerk_jwks_url)
            response.raise_for_status()
        header = jwt.get_unverified_header(credentials.credentials)
        keys = response.json().get("keys", [])
        signing_key = next(
            (
                key
                for key in keys
                if key.get("kid") == header.get("kid") and key.get("kty") == "RSA"
            ),
            None,
        )
        if signing_key is None:
            raise JWTError("JWT signing key is unavailable")
        payload = jwt.decode(
            credentials.credentials,
            signing_key,
            algorithms=["RS256"],
            issuer=settings.clerk_issuer,
            options={"verify_aud": False},
        )
        subject = payload.get("sub")
        if not isinstance(subject, str) or not subject:
            raise JWTError("JWT subject is missing")
    except (httpx.HTTPError, ValueError, JWTError) as error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="The bearer token is invalid.",
        ) from error
    return Principal(subject=subject)
