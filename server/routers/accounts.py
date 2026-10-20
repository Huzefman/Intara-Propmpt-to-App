"""Instant account creation.

Supabase projects default to "Confirm email" ON, which makes signUp return no
session until the visitor clicks a link. The product decision for Intara is
frictionless accounts ("no email confirmation"), so this endpoint creates a
pre-confirmed user with the service key. The browser then signs in with the
same credentials via supabase-js and holds the session.

This is an intentional demo trade-off: account creation does not prove email
ownership. Keep it rate-limited; add captcha / invite codes before real use.
"""
from __future__ import annotations

import re
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

router = APIRouter()

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_SIGNUPS: dict[str, list[float]] = {}
_SIGNUP_LIMIT = 10          # accounts per IP…
_SIGNUP_WINDOW = 3600.0     # …per hour


def _check_signup_rate(ip: str) -> None:
    now = time.time()
    for key, stamps in list(_SIGNUPS.items()):
        _SIGNUPS[key] = [t for t in stamps if now - t < _SIGNUP_WINDOW]
    stamps = _SIGNUPS.get(ip, [])
    if len(stamps) >= _SIGNUP_LIMIT:
        raise HTTPException(429, "Too many accounts from this address — try again later.")
    stamps.append(now)
    _SIGNUPS[ip] = stamps


class SignupIn(BaseModel):
    email: str
    password: str


@router.post("/auth/signup", status_code=201)
def signup(body: SignupIn, request: Request):
    email = (body.email or "").strip().lower()
    password = body.password or ""
    if not _EMAIL_RE.match(email):
        raise HTTPException(400, "Enter a valid email address.")
    if len(password) < 6:
        raise HTTPException(400, "Use at least 6 characters for the password.")
    if len(password) > 200:
        raise HTTPException(400, "Password is too long.")

    # Render/Vercel sit in front of us: prefer the first X-Forwarded-For hop so
    # one proxy address doesn't rate-limit every visitor together.
    fwd = request.headers.get("x-forwarded-for", "")
    ip = fwd.split(",")[0].strip() if fwd else (
        request.client.host if request.client else "unknown"
    )
    _check_signup_rate(ip)

    try:
        from db.wishes import _client
        res = _client().auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
        })
        user = getattr(res, "user", None)
    except Exception as e:
        msg = str(e)
        lower = msg.lower()
        if "already" in lower or "registered" in lower or "exists" in lower:
            raise HTTPException(409, "An account with this email already exists — sign in instead.")
        if "invalid" in lower and "email" in lower:
            raise HTTPException(400, "That email address is not accepted.")
        print(f"signup failed: {msg[:300]}")
        raise HTTPException(500, "Could not create the account — try again in a moment.")

    if user is None:
        raise HTTPException(500, "Could not create the account — try again in a moment.")
    return {"ok": True, "id": str(getattr(user, "id", "")), "email": getattr(user, "email", email)}
