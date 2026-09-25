from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.auth import create_access_token, get_current_reviewer, verify_password
from api.dependencies import get_db
from api.schemas.auth import LoginRequest, TokenResponse, UserOut
from db.models import Reviewer

router = APIRouter()


@router.post("/login", response_model=TokenResponse)
async def login(payload: LoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Reviewer).where(Reviewer.email == payload.email))
    reviewer = result.scalar_one_or_none()
    if reviewer is None or not verify_password(payload.password, reviewer.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password")

    token = create_access_token(reviewer)
    return TokenResponse(token=token, user=UserOut.model_validate(reviewer))


@router.get("/me", response_model=UserOut)
async def me(reviewer: Reviewer = Depends(get_current_reviewer)):
    return UserOut.model_validate(reviewer)
