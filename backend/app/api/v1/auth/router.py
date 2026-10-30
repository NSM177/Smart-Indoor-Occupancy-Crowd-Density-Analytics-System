"""Module 1 Router: Authentication, Token Lifecycle & User Account Management."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, status
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.security import (
    bearer_scheme,
    get_current_user,
    require_admin,
)
from app.database.session import get_db
from app.models.entities import User
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    TokenResponse,
    UserCreateRequest,
    UserResponse,
)
from app.services.business_services import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication & Authorization"])


@router.post("/login", response_model=TokenResponse)
def login(
    dto: LoginRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return AuthService(db).login(dto)


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    dto: RefreshTokenRequest,
    db: Session = Depends(get_db),
) -> TokenResponse:
    return AuthService(db).refresh_tokens(dto.refresh_token)


@router.post("/logout")
def logout(
    dto: Optional[LogoutRequest] = None,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    _current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    access_tok = credentials.credentials if credentials else None
    refresh_tok = dto.refresh_token if dto else None
    return AuthService(db).logout(access_tok, refresh_tok)


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)) -> UserResponse:
    return UserResponse.model_validate(current_user)


@router.get("/users", response_model=List[UserResponse])
def list_users(
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> List[UserResponse]:
    return AuthService(db).list_users()


@router.post(
    "/users",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_user(
    dto: UserCreateRequest,
    _admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> UserResponse:
    return AuthService(db).create_user(dto)
