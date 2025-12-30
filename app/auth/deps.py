import os

from fastapi import Request, HTTPException
from jose import jwt, JWTError
from app.database.config import settings


def _get_jwt_settings():
    secret = getattr(settings, "JWT_SECRET", None) or os.environ.get("JWT_SECRET")
    alg = getattr(settings, "JWT_ALGORITHM", "HS256")
    ttl_min = getattr(settings, "ACCESS_TOKEN_EXPIRE_MINUTES", 525600)
    if not secret:
        raise HTTPException(status_code=500, detail="Server misconfigured: JWT_SECRET not set")
    try:
        ttl_min = int(ttl_min)
    except Exception:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: ACCESS_TOKEN_EXPIRE_MINUTES must be an integer",
        )
    if ttl_min <= 0:
        raise HTTPException(
            status_code=500,
            detail="Server misconfigured: ACCESS_TOKEN_EXPIRE_MINUTES must be > 0",
        )
    settings.JWT_SECRET = secret
    return secret, alg, ttl_min


async def get_current_user_id(request: Request) -> str:
    auth = request.headers.get("Authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth.split(" ", 1)[1]
        secret, alg, _ = _get_jwt_settings()
        try:
            payload = jwt.decode(token, secret, algorithms=[alg])
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")

        jti = payload.get("jti")
        revoked = getattr(request.app, "revoked_jti", set())
        if jti in revoked:
            raise HTTPException(status_code=401, detail="Token revoked")

        user_id = payload.get("sub")
        if not user_id:
            raise HTTPException(status_code=401, detail="Invalid token subject")
        return user_id

    header_user = request.headers.get("X-User-ID")
    if header_user:
        return header_user

    raise HTTPException(status_code=400, detail="Missing user identity")
