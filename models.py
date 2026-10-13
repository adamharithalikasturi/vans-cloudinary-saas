from datetime import datetime, timezone

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String

from db import Base


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), default="")
    company = Column(String(255), default="")
    password_hash = Column(String(512), nullable=False)
    role = Column(String(20), default="user", nullable=False)        # "user" | "admin"
    is_active = Column(Boolean, default=True, nullable=False)
    monthly_limit = Column(Integer, nullable=True)                    # products per month; NULL = unlimited
    created_at = Column(DateTime, default=utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class SessionToken(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    token_hash = Column(String(64), unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=False)


class UsageLog(Base):
    __tablename__ = "usage_logs"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    brand = Column(String(40), default="")
    source = Column(String(255), default="")
    items_count = Column(Integer, default=0, nullable=False)
    images_found = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime, default=utcnow, nullable=False, index=True)
