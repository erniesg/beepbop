from __future__ import annotations

from typing import Any

import httpx
from authlib.integrations.starlette_client import OAuth
from fastapi import HTTPException, Request

from app.config import get_settings
from app.db import upsert_user


_oauth: OAuth | None = None


def get_oauth() -> OAuth:
    global _oauth
    if _oauth is None:
        from app.app_settings import google_client_id, google_client_secret
        oauth = OAuth()
        oauth.register(
            name="google",
            client_id=google_client_id(),
            client_secret=google_client_secret(),
            server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
            client_kwargs={"scope": "openid email profile"},
        )
        _oauth = oauth
    return _oauth


async def exchange_code(request: Request) -> dict[str, Any]:
    """Complete the OAuth flow and return a user profile dict."""
    oauth = get_oauth()
    token = await oauth.google.authorize_access_token(request)
    # userinfo is included via the 'openid email profile' scope
    userinfo = token.get("userinfo")
    if not userinfo:
        # fallback: fetch userinfo manually
        async with httpx.AsyncClient() as client:
            r = await client.get(
                "https://openidconnect.googleapis.com/v1/userinfo",
                headers={"Authorization": f"Bearer {token['access_token']}"},
            )
            r.raise_for_status()
            userinfo = r.json()
    return {
        "email": userinfo["email"],
        "name": userinfo.get("name"),
        "picture": userinfo.get("picture"),
    }


async def login_user(request: Request, profile: dict[str, Any]) -> dict:
    """Upsert user + set session."""
    user = upsert_user(profile["email"], profile.get("name"), profile.get("picture"))
    request.session["user_id"] = user["id"]
    return user


def current_user(request: Request) -> dict | None:
    from app.db import get_user
    uid = request.session.get("user_id")
    if not uid:
        return None
    return get_user(uid)


def require_user(request: Request) -> dict:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user
