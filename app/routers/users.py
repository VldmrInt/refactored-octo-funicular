from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.auth import create_jwt, determine_role, validate_init_data
from app.database import get_db
from app.dependencies import get_current_user
from app.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


class TelegramAuthRequest(BaseModel):
    initData: str


class UserOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    full_name: str
    role: str

    model_config = {"from_attributes": True}


class AuthResponse(BaseModel):
    token: str
    user: UserOut


@router.post("/telegram", response_model=AuthResponse)
def auth_telegram(payload: TelegramAuthRequest, db: Session = Depends(get_db)):
    try:
        tg_user = validate_init_data(payload.initData)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc))

    telegram_id: int = tg_user["id"]
    username: str | None = tg_user.get("username")
    first_name: str = tg_user.get("first_name", "")
    last_name: str = tg_user.get("last_name", "")
    full_name = f"{first_name} {last_name}".strip() or username or str(telegram_id)

    user = db.query(User).filter(User.telegram_id == telegram_id).first()
    role = determine_role(telegram_id)

    if user is None:
        user = User(
            telegram_id=telegram_id,
            username=username,
            full_name=full_name,
            role=role,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    else:
        # Update profile info and role on each login
        user.username = username
        user.full_name = full_name
        user.role = role
        db.commit()
        db.refresh(user)

    token = create_jwt(user.id, user.telegram_id, user.role)
    return AuthResponse(token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def get_me(current_user: User = Depends(get_current_user)):
    return UserOut.model_validate(current_user)
