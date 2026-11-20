# EventHub - Event Management System (Python / Flask)

A complete event management web app written entirely in Python (Flask + Jinja2 templates).
No JavaScript is used: pages are server-rendered, charts are SVG generated from Python data.

## Features
**Attendees**
- Browse upcoming / past events, search, filter by category, free-only, pagination
- One-click registration with a unique ticket code
- Automatic waitlist when an event is full, with queue position
- Auto-promotion from the waitlist when someone cancels or capacity increases
- "My tickets" page

**Organizers**
- Create, edit, cancel and delete events (validation + ownership checks)
- Dashboard: events, upcoming, registrations, waitlisted, seats-filled %, per-event chart
- Attendee list, check-in / undo check-in, CSV export

**Platform**
- Register / login / logout with hashed passwords
- CSRF protection, XSS-safe output, CSP headers, open-redirect protection, CSV-injection protection
- Public JSON API: /api/events, /api/events/<id>, /api/health
- 15 automated tests (pytest)

## Tech stack
Python 3, Flask, Jinja2, Flask-SQLAlchemy (ORM), Flask-Login, SQLite (default) or PostgreSQL (RDS),
Gunicorn, AWS Elastic Beanstalk.

## Database design
    users(id, name, email*, password_hash, created_at)
    events(id, organizer_id -> users, title, description, category, venue, starts_at, ends_at,
           capacity, price, status[published|cancelled], created_at)
    registrations(id, event_id -> events, user_id -> users, status[confirmed|waitlisted|cancelled],
                  ticket_code*, checked_in, created_at)   UNIQUE(event_id, user_id)

## Project structure
    application.py     Elastic Beanstalk entry point
    Procfile           gunicorn command
    app/__init__.py    app factory, filters, security headers, error pages
    app/models.py      User, Event, Registration
    app/services.py    capacity, waitlist and registration rules
    app/views.py       all pages (browse, detail, register, organizer tools)
    app/auth.py        signup / login / logout
    app/api.py         public JSON API
    app/seed.py        optional demo data
    app/templates/     Jinja2 pages        app/static/  CSS
    tests/             pytest suite

## Run locally
    python -m venv .venv
    source .venv/bin/activate          (Windows: .venv\Scripts\activate)
    pip install -r requirements.txt
    SEED_DEMO=1 python application.py  (Windows PowerShell: $env:SEED_DEMO="1"; python application.py)
    open http://localhost:8000
    pip install pytest && python -m pytest

## Deploy on AWS Elastic Beanstalk (Console)
1. Zip so application.py, Procfile, requirements.txt are at the ROOT of the zip.
2. Elastic Beanstalk > Create application > Web server environment, platform Python,
   upload the zip, preset "Single instance (free tier eligible)".
   (Existing environment: Upload and deploy > choose the zip.)
3. Open the Domain link using http:// (not https://).

### Environment properties (Configuration > Updates, monitoring, and logging > Edit)
| Name | Value | Purpose |
|---|---|---|
| SECRET_KEY | long random string | required for secure sessions |
| APP_TZ | Asia/Kolkata | time zone used to decide upcoming/past (default already Asia/Kolkata) |
| SEED_DEMO | 1 | optional: loads 6 sample events + demo organizer (demo@eventhub.com / demo12345). Remove after demo. |
| DATABASE_URL | postgresql://USER:PASS@HOST:5432/DB | optional: use RDS PostgreSQL for permanent data |

## Data persistence
With the default SQLite database, data may be lost on redeploy. For permanent storage create an
RDS PostgreSQL instance, allow the Beanstalk security group to reach port 5432, and set DATABASE_URL.
No code change is needed (SQLAlchemy).

## Concurrency note
Registration locks the event row (SELECT ... FOR UPDATE on PostgreSQL) so two users cannot take
the last seat at the same time.

## Future work (good for viva)
Email confirmations (AWS SES), QR-code tickets, online payments (Razorpay), admin role,
image uploads (S3), reminders via scheduled jobs, Docker + CI/CD, Alembic migrations.

## Cleanup
Terminate the environment (Actions > Terminate environment) to avoid charges.
