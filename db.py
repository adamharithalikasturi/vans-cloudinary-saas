import os
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

# SQLite for local development; set DATABASE_URL to a PostgreSQL URL in production
# (Supabase, Neon, Railway, Render, RDS...).
# Vercel's database integrations may name the variable POSTGRES_URL instead of DATABASE_URL.
DATABASE_URL = (os.getenv("DATABASE_URL") or os.getenv("POSTGRES_URL") or "").strip() or "sqlite:///./app.db"
if DATABASE_URL.startswith("sqlite:///./") and not os.access(".", os.W_OK):
    # Read-only filesystem (some serverless hosts): fall back to a temp file so the app can still start.
    # Data stored here is NOT permanent. Set DATABASE_URL to PostgreSQL for real use.
    print("[setup] WARNING: project folder is read-only; using a temporary SQLite database. Set DATABASE_URL.")
    DATABASE_URL = "sqlite:////tmp/app.db"
# Be explicit about the driver: newer SQLAlchemy versions default "postgresql://" to psycopg v3,
# but requirements.txt installs psycopg2.
for prefix in ("postgres://", "postgresql://"):
    if DATABASE_URL.startswith(prefix):
        DATABASE_URL = "postgresql+psycopg2://" + DATABASE_URL[len(prefix):]
        break

# Some integrations append options (e.g. "supa=...") that the PostgreSQL driver rejects.
if DATABASE_URL.startswith("postgresql"):
    _parts = urlsplit(DATABASE_URL)
    _query = urlencode([(k, v) for k, v in parse_qsl(_parts.query) if k not in ("supa",)])
    DATABASE_URL = urlunsplit(_parts._replace(query=_query))

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, pool_recycle=300, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
