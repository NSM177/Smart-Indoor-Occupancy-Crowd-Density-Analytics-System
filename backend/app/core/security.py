"""
Security utilities for Authentication & Role-Based Access Control (RBAC).
Provides:
- Password hashing & verification (PBKDF2-HMAC-SHA256 with cryptographic salt)
- JWT Access Token & Refresh Token creation & decoding
- Token revocation blocklist for Logout
- FastAPI dependencies for `ADMIN` and `OPERATOR` role enforcement
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import hmac
import secrets
from typing import Any, Dict, Optional, Set
import uuid

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import jwt
from sqlalchemy.orm import Session

from app.core.config import settings
from app.database.session import get_db
from app.models.entities import User

bearer_scheme = HTTPBearer(auto_error=False)
_REVOKED_TOKENS: Set[str] = set()


def hash_password(plain_password: str) -> str:
    """Hash a plain-text password using PBKDF2-HMAC-SHA256 with a 16-byte random salt."""
    salt = secrets.token_hex(16)
    iterations = 120_000
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        plain_password.encode("utf-8"),
        salt.encode("utf-8"),
        iterations,
    ).hex()
    return f"pbkdf2_sha256${iterations}${salt}${derived}"


def verify_password(plain_password: str, stored_hash: str) -> bool:
    """Constant-time verification of plain password against stored PBKDF2 hash."""
    try:
        scheme, iter_str, salt, expected_hex = stored_hash.split("$", 3)
        if scheme != "pbkdf2_sha256":
            return False
        iterations = int(iter_str)
        candidate = hashlib.pbkdf2_hmac(
            "sha256",
            plain_password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        ).hex()
        return hmac.compare_digest(candidate, expected_hex)
    except Exception:
        return False


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta
        or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    )
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "access",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def create_refresh_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (
        expires_delta or timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    )
    payload: Dict[str, Any] = {
        "sub": str(user_id),
        "username": username,
        "role": role,
        "type": "refresh",
        "jti": str(uuid.uuid4()),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
    }
    return jwt.encode(
        payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM
    )


def decode_jwt_token(token: str, expected_type: Optional[str] = None) -> Dict[str, Any]:
    if token in _REVOKED_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked (logged out).",
        )
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
        )
    except jwt.ExpiredSignatureError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
        ) from exc
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid authentication token.",
        ) from exc

    jti = payload.get("jti")
    if jti and jti in _REVOKED_TOKENS:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has been revoked.",
        )

    if expected_type and payload.get("type") != expected_type:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token type: expected '{expected_type}'.",
        )
    return payload


def revoke_token(token: str) -> None:
    """Add token and its jti to the revocation blocklist."""
    _REVOKED_TOKENS.add(token)
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        if "jti" in payload:
            _REVOKED_TOKENS.add(str(payload["jti"]))
    except Exception:
        pass


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated. Missing Bearer token.",
        )
    payload = decode_jwt_token(credentials.credentials, expected_type="access")
    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == str(user_id)).first()
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account not found or inactive.",
        )
    return user


def get_optional_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """Return authenticated User if Bearer token is provided, or None otherwise."""
    if credentials is None or not credentials.credentials:
        return None
    try:
        payload = decode_jwt_token(credentials.credentials, expected_type="access")
        user_id = payload.get("sub")
        user = db.query(User).filter(User.id == str(user_id)).first()
        return user if (user and user.is_active) else None
    except HTTPException:
        return None


def require_admin(current_user: User = Depends(get_current_user)) -> User:
    if current_user.role != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin privileges required for this operation.",
        )
    return current_user


def require_operator_or_admin(
    current_user: User = Depends(get_current_user),
) -> User:
    if current_user.role not in ("ADMIN", "OPERATOR"):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Operator or Admin privileges required.",
        )
    return current_user
