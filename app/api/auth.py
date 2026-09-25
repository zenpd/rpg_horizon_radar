"""Auth — named-reviewer JWT, replacing the accelerator's default EntraID stub.

RPG Horizon Radar's access model is the product's core requirement (see
DESIGN.md §4/§8), not an accelerator afterthought: a small, named, auditable
reviewer allow-list, never "anyone with a login." There is deliberately no
signup/registration endpoint anywhere in this API — reviewers are created only
by a ``compliance_admin`` via ``api/routers/reviewers.py``.

If a future deployment needs EntraID SSO on top of this, front it at the
reviewer-provisioning step (map an Entra identity to a named ``Reviewer`` row),
not by loosening this module back to "any authenticated token is fine."
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
    return _pwd_context.verify(raw_password, password_hash)


def create_access_token(reviewer: Reviewer) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(reviewer.id),
        "role": reviewer.role,
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Reviewer no longer exists")

    return reviewer


def require_role(required_role: str):
    def _dependency(reviewer: Reviewer = Depends(get_current_reviewer)) -> Reviewer:
        if reviewer.role != required_role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires role '{required_role}'"
            )
        return reviewer

    return _dependency
