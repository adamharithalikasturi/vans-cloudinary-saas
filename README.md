# vans-cloudinary-saas
# Asset Intelligence

Catalog imagery coverage platform with customer accounts, usage limits and an admin dashboard.

## Run locally

    pip install -r requirements.txt
    cp .env.example .env          # then edit ADMIN_EMAIL / ADMIN_PASSWORD
    export $(grep -v '^#' .env | xargs)   # or set the variables in your host's dashboard
    uvicorn main:app --host 0.0.0.0 --port 8000

Open http://localhost:8000 and sign in with ADMIN_EMAIL / ADMIN_PASSWORD.
Tables are created automatically on first start.

## Database

- Default: SQLite file `app.db` (development only).
- Production: set `DATABASE_URL` to a PostgreSQL connection string (Supabase, Neon, Railway, Render...).
  Hosts with ephemeral disks (Render free, Heroku, Railway without a volume) lose SQLite data on every deploy, so use PostgreSQL there.

## Accounts

- Access is by invitation: the admin creates customers at `/admin.html` (email, password, monthly product limit).
- Limit is counted in products per calendar month (UTC). Blank limit = unlimited.
- Admins can disable accounts, reset passwords and see per-customer usage and recent activity.

## Regional image sources

`brands/timberland.py` -> `REGIONAL_SOURCES` is empty until market image URL patterns are confirmed.
Add an entry per market (see the comment in that file). Products with no imagery on the main servers are then
checked against these sources automatically.

## Production notes

- Serve over HTTPS (the session cookie is marked Secure automatically behind a proxy that sends X-Forwarded-Proto).
- If you scale to more than one server process, move the login throttle in `auth.py` to a shared store.
