"""Auth — named-user JWT, replacing the accelerator's default EntraID stub.

Every user who can sign in sees everything; there are no roles (DESIGN.md §4).
There is no signup endpoint: users are added by another signed-in user via
``api/routers/reviewers.py``, and the first one comes from FIRST_USER_EMAIL /
FIRST_USER_PASSWORD (db/seed.py).

If a future deployment needs EntraID SSO, map an Entra identity to a
``Reviewer`` row at sign-in.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.dependencies import get_db
from db.models import Reviewer
from shared.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
_bearer_scheme = HTTPBearer(auto_error=False)

JWT_ALGORITHM = "HS256"
JWT_EXPIRES_MINUTES = 60 * 12


def hash_password(raw_password: str) -> str:
    return _pwd_context.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return _pwd_context.verify(raw_password, password_hash)
    except ValueError:  # not a bcrypt hash, e.g. a login disabled by migration 0004
        return False


def create_access_token(reviewer: Reviewer) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(reviewer.id),
        "name": reviewer.name,
        "email": reviewer.email,
        "iat": now,
        "exp": now + timedelta(minutes=JWT_EXPIRES_MINUTES),
    }
    return jwt.encode(payload, settings.app_secret_key, algorithm=JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.app_secret_key, algorithms=[JWT_ALGORITHM])
    except JWTError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from exc


async def get_current_reviewer(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> Reviewer:
    if creds is None or not creds.credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")

    payload = decode_access_token(creds.credentials)
    reviewer_id = payload.get("sub")
    if reviewer_id is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    result = await db.execute(select(Reviewer).where(Reviewer.id == int(reviewer_id)))
    reviewer = result.scalar_one_or_none()
    if reviewer is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User no longer exists")

    return reviewer
