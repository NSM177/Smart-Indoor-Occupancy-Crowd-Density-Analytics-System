"""Pydantic v2 schemas for Authentication & User Management (Module 1)."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional
from pydantic import BaseModel, ConfigDict, EmailStr, Field


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=4, max_length=128)


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(..., min_length=10, alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class LogoutRequest(BaseModel):
    refresh_token: Optional[str] = Field(default=None, alias="refreshToken")

    model_config = ConfigDict(populate_by_name=True)


class UserCreateRequest(BaseModel):
    username: str = Field(..., min_length=3, max_length=64)
    email: str = Field(..., min_length=5, max_length=128)
    password: str = Field(..., min_length=6, max_length=128)
    full_name: str = Field(default="", max_length=128, alias="fullName")
    role: Literal["ADMIN", "OPERATOR"] = Field(default="OPERATOR")

    model_config = ConfigDict(populate_by_name=True)


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserResponse
