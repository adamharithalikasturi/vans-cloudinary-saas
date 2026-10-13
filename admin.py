from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import EMAIL_RE, admin_user, month_start
from db import get_db
from models import SessionToken, UsageLog, User
from security import hash_password

router = APIRouter(prefix="/api/v1/admin", tags=["admin"])


class NewUser(BaseModel):
    email: str
    password: str
    name: str = ""
    company: str = ""
    role: str = "user"
    monthly_limit: Optional[int] = None


class UpdateUser(BaseModel):
    name: Optional[str] = None
    company: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    monthly_limit: Optional[int] = None      # send null to make unlimited
    password: Optional[str] = None


def _check_password(pw):
    if len(pw) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters.")


def _check_role(role):
    if role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="Role must be 'user' or 'admin'.")


@router.get("/stats")
def stats(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    ms = month_start()
    return {
        "users": db.query(func.count(User.id)).scalar(),
        "active_users": db.query(func.count(User.id)).filter(User.is_active.is_(True)).scalar(),
        "products_this_month": int(db.query(func.coalesce(func.sum(UsageLog.items_count), 0)).filter(UsageLog.created_at >= ms).scalar() or 0),
        "runs_this_month": db.query(func.count(UsageLog.id)).filter(UsageLog.created_at >= ms).scalar(),
        "products_total": int(db.query(func.coalesce(func.sum(UsageLog.items_count), 0)).scalar() or 0),
    }


@router.get("/users")
def list_users(_: User = Depends(admin_user), db: Session = Depends(get_db)):
    ms = month_start()
    month = dict(
        db.query(UsageLog.user_id, func.coalesce(func.sum(UsageLog.items_count), 0))
        .filter(UsageLog.created_at >= ms).group_by(UsageLog.user_id).all()
    )
    total = dict(
        db.query(UsageLog.user_id, func.coalesce(func.sum(UsageLog.items_count), 0))
        .group_by(UsageLog.user_id).all()
    )
    out = []
    for u in db.query(User).order_by(User.created_at.desc()).all():
        out.append({
            "id": u.id, "email": u.email, "name": u.name or "", "company": u.company or "",
            "role": u.role, "is_active": u.is_active, "monthly_limit": u.monthly_limit,
            "used_this_month": int(month.get(u.id, 0)), "used_total": int(total.get(u.id, 0)),
            "created_at": u.created_at.isoformat() + "Z",
            "last_login_at": (u.last_login_at.isoformat() + "Z") if u.last_login_at else None,
        })
    return out


@router.post("/users")
def create_user(body: NewUser, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    email = body.email.strip().lower()
    if not EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="Please enter a valid email address.")
    _check_password(body.password)
    _check_role(body.role)
    if body.monthly_limit is not None and body.monthly_limit < 0:
        raise HTTPException(status_code=400, detail="Monthly limit cannot be negative.")
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(status_code=409, detail="A user with this email already exists.")
    u = User(email=email, name=body.name.strip(), company=body.company.strip(), role=body.role,
             monthly_limit=body.monthly_limit, password_hash=hash_password(body.password))
    db.add(u)
    db.commit()
    return {"id": u.id}


@router.patch("/users/{user_id}")
def update_user(user_id: int, body: UpdateUser, admin: User = Depends(admin_user), db: Session = Depends(get_db)):
    u = db.get(User, user_id)
    if not u:
        raise HTTPException(status_code=404, detail="User not found.")
    data = body.model_dump(exclude_unset=True)

    if u.id == admin.id and (data.get("is_active") is False or data.get("role") == "user"):
        raise HTTPException(status_code=400, detail="You cannot deactivate or demote your own account.")
    if "role" in data:
        _check_role(data["role"]); u.role = data["role"]
    if "name" in data and data["name"] is not None:
        u.name = data["name"].strip()
    if "company" in data and data["company"] is not None:
        u.company = data["company"].strip()
    if "monthly_limit" in data:
        if data["monthly_limit"] is not None and data["monthly_limit"] < 0:
            raise HTTPException(status_code=400, detail="Monthly limit cannot be negative.")
        u.monthly_limit = data["monthly_limit"]
    if data.get("password"):
        _check_password(data["password"])
        u.password_hash = hash_password(data["password"])
        db.query(SessionToken).filter(SessionToken.user_id == u.id).delete()
    if "is_active" in data and data["is_active"] is not None:
        u.is_active = data["is_active"]
        if not u.is_active:
            db.query(SessionToken).filter(SessionToken.user_id == u.id).delete()
    db.commit()
    return {"ok": True}


@router.get("/activity")
def activity(limit: int = 100, _: User = Depends(admin_user), db: Session = Depends(get_db)):
    rows = (
        db.query(UsageLog, User.email)
        .join(User, User.id == UsageLog.user_id)
        .order_by(UsageLog.created_at.desc())
        .limit(min(max(limit, 1), 500))
        .all()
    )
    return [{
        "email": email, "brand": l.brand, "source": l.source, "items": l.items_count,
        "images_found": l.images_found, "at": l.created_at.isoformat() + "Z",
    } for l, email in rows]
