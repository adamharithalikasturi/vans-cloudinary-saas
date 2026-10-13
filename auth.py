import re
import time
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from db import get_db
from models import SessionToken, UsageLog, User, utcnow
from security import DUMMY_HASH, hash_token, new_token, verify_password

COOKIE = "ai_session"
SESSION_DAYS = 7
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# --- very small in-memory brute-force throttle (per email + IP) -------------
_FAILS: dict = {}
MAX_FAILS, WINDOW = 6, 15 * 60


def _throttled(key):
    now = time.time()
    _FAILS[key] = [t for t in _FAILS.get(key, []) if now - t < WINDOW]
    return len(_FAILS[key]) >= MAX_FAILS


def _fail(key):
    _FAILS.setdefault(key, []).append(time.time())


# --- dependencies ------------------------------------------------------------
def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(status_code=401, detail="Please sign in to continue.")
    sess = db.query(SessionToken).filter(SessionToken.token_hash == hash_token(token)).first()
    if not sess or sess.expires_at < utcnow():
        raise HTTPException(status_code=401, detail="Your session has expired. Please sign in again.")
    user = db.get(User, sess.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is not active.")
    return user


def admin_user(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Administrator access is required.")
    return user


# --- usage -------------------------------------------------------------------
def month_start():
    n = utcnow()
    return n.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def usage_for(db: Session, user: User):
    used = (
        db.query(func.coalesce(func.sum(UsageLog.items_count), 0))
        .filter(UsageLog.user_id == user.id, UsageLog.created_at >= month_start())
        .scalar()
    )
    return int(used or 0), user.monthly_limit


def user_payload(db: Session, user: User):
    used, limit = usage_for(db, user)
    return {
        "id": user.id,
        "email": user.email,
        "name": user.name or "",
        "company": user.company or "",
        "role": user.role,
        "usage": {"used": used, "limit": limit},
    }


# --- routes ------------------------------------------------------------------
class LoginBody(BaseModel):
    email: str
    password: str


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    ip = request.client.host if request.client else "?"
    key = f"{email}|{ip}"
    if _throttled(key):
        raise HTTPException(status_code=429, detail="Too many attempts. Please wait a few minutes and try again.")

    user = db.query(User).filter(User.email == email).first()
    ok = verify_password(body.password, user.password_hash if user else DUMMY_HASH)
    if not user or not ok or not user.is_active:
        _fail(key)
        raise HTTPException(status_code=401, detail="Incorrect email or password.")

    token = new_token()
    db.add(SessionToken(token_hash=hash_token(token), user_id=user.id, expires_at=utcnow() + timedelta(days=SESSION_DAYS)))
    user.last_login_at = utcnow()
    db.commit()
    _FAILS.pop(key, None)

    secure = request.headers.get("x-forwarded-proto", request.url.scheme) == "https"
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=secure, max_age=SESSION_DAYS * 86400, path="/")
    return user_payload(db, user)


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(COOKIE)
    if token:
        db.query(SessionToken).filter(SessionToken.token_hash == hash_token(token)).delete()
        db.commit()
    response.delete_cookie(COOKIE, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return user_payload(db, user)
