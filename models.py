import os
import secrets
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

CATEGORIES = ("Technical", "Cultural", "Sports", "Workshop", "Seminar", "Social", "Other")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


def now_local():
    """Current time in the event time zone (APP_TZ env var, default Asia/Kolkata), naive."""
    try:
        tz = ZoneInfo(os.environ.get("APP_TZ", "Asia/Kolkata"))
    except Exception:
        tz = timezone.utc
    return datetime.now(tz).replace(tzinfo=None)


def new_ticket_code():
    return secrets.token_hex(4).upper()


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    events = db.relationship("Event", backref="organizer", cascade="all, delete-orphan", lazy="dynamic")
    registrations = db.relationship("Registration", backref="user", cascade="all, delete-orphan", lazy="dynamic")

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)


class Event(db.Model):
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    organizer_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.String(2000), default="", nullable=False)
    category = db.Column(db.String(40), default="Other", nullable=False, index=True)
    venue = db.Column(db.String(120), nullable=False)
    starts_at = db.Column(db.DateTime, nullable=False, index=True)
    ends_at = db.Column(db.DateTime, nullable=True)
    capacity = db.Column(db.Integer, nullable=False)
    price = db.Column(db.Integer, default=0, nullable=False)  # in rupees, 0 = free
    status = db.Column(db.String(12), default="published", nullable=False)  # published / cancelled
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)

    registrations = db.relationship(
        "Registration", backref="event", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def is_past(self):
        return (self.ends_at or self.starts_at) < now_local()

    @property
    def is_cancelled(self):
        return self.status == "cancelled"

    @property
    def is_open(self):
        return self.status == "published" and not self.is_past


class Registration(db.Model):
    __tablename__ = "registrations"
    __table_args__ = (db.UniqueConstraint("event_id", "user_id", name="uq_event_user"),)

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    status = db.Column(db.String(12), default="confirmed", nullable=False)  # confirmed / waitlisted / cancelled
    ticket_code = db.Column(db.String(16), unique=True, nullable=False, default=new_ticket_code)
    checked_in = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow, nullable=False)
