import csv
import io
from datetime import datetime

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from . import services
from .models import CATEGORIES, Event, Registration, db, now_local

bp = Blueprint("views", __name__)
PER_PAGE = 9
EVENT_FIELDS = ("title", "description", "category", "venue", "starts_at", "ends_at", "capacity", "price")


# ---------------- helpers ----------------
def parse_dt(raw):
    try:
        return datetime.fromisoformat(raw)
    except (TypeError, ValueError):
        return None


def clean_event(form, creating):
    """Validate the event form. Returns (clean_data, errors)."""
    out, errors = {}, {}

    title = form.get("title", "").strip()
    if not 3 <= len(title) <= 120:
        errors["title"] = "Title must be 3 to 120 characters"
    out["title"] = title

    description = form.get("description", "").strip()
    if len(description) > 2000:
        errors["description"] = "Description is limited to 2000 characters"
    out["description"] = description

    category = form.get("category", "")
    if category not in CATEGORIES:
        errors["category"] = "Choose a valid category"
    out["category"] = category

    venue = form.get("venue", "").strip()
    if not 2 <= len(venue) <= 120:
        errors["venue"] = "Venue must be 2 to 120 characters"
    out["venue"] = venue

    starts = parse_dt(form.get("starts_at", ""))
    if starts is None:
        errors["starts_at"] = "Enter a valid start date and time"
    elif creating and starts < now_local():
        errors["starts_at"] = "Start time must be in the future"
    out["starts_at"] = starts

    ends = None
    if form.get("ends_at", "").strip():
        ends = parse_dt(form.get("ends_at"))
        if ends is None:
            errors["ends_at"] = "Enter a valid end date and time"
        elif starts and ends <= starts:
            errors["ends_at"] = "End time must be after the start time"
    out["ends_at"] = ends

    try:
        capacity = int(form.get("capacity", ""))
        if not 1 <= capacity <= 100000:
            raise ValueError
        out["capacity"] = capacity
    except ValueError:
        errors["capacity"] = "Capacity must be a whole number from 1 to 100000"

    try:
        price = int(form.get("price", "0") or 0)
        if not 0 <= price <= 100000:
            raise ValueError
        out["price"] = price
    except ValueError:
        errors["price"] = "Price must be a whole number (0 for free)"

    return out, errors


def owner_event(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404, description="Event not found")
    if event.organizer_id != current_user.id:
        abort(403, description="Only the organizer can do this")
    return event


def event_query(args):
    q = Event.query
    end_or_start = db.func.coalesce(Event.ends_at, Event.starts_at)
    when = args.get("when", "upcoming")
    if when == "past":
        q = q.filter(end_or_start < now_local()).order_by(Event.starts_at.desc())
    elif when == "all":
        q = q.order_by(Event.starts_at.desc())
    else:
        q = q.filter(end_or_start >= now_local()).order_by(Event.starts_at.asc())

    if args.get("category") in CATEGORIES:
        q = q.filter(Event.category == args["category"])
    if args.get("free") == "1":
        q = q.filter(Event.price == 0)
    term = (args.get("q") or "").strip()
    if term:
        q = q.filter(db.or_(
            Event.title.icontains(term, autoescape=True),
            Event.venue.icontains(term, autoescape=True),
            Event.description.icontains(term, autoescape=True),
        ))
    return q


# ---------------- public pages ----------------
@bp.get("/")
def index():
    args = request.args
    page = max(args.get("page", 1, type=int), 1)
    result = event_query(args).paginate(page=page, per_page=PER_PAGE, error_out=False)
    cnt = services.counts([e.id for e in result.items])
    filters = {k: args.get(k) for k in ("q", "category", "when", "free") if args.get(k)}
    return render_template("index.html", result=result, cnt=cnt, filters=filters, categories=CATEGORIES)


@bp.get("/events/<int:event_id>")
def event_detail(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404, description="Event not found")
    cnt = services.counts([event.id])[event.id]
    my_reg, position = None, None
    if current_user.is_authenticated:
        my_reg = Registration.query.filter_by(event_id=event.id, user_id=current_user.id).first()
        if my_reg and my_reg.status == "waitlisted":
            position = Registration.query.filter(
                Registration.event_id == event.id,
                Registration.status == "waitlisted",
                db.or_(
                    Registration.created_at < my_reg.created_at,
                    db.and_(Registration.created_at == my_reg.created_at, Registration.id < my_reg.id),
                ),
            ).count() + 1
    is_owner = current_user.is_authenticated and current_user.id == event.organizer_id
    return render_template("event_detail.html", event=event, cnt=cnt, my_reg=my_reg,
                           position=position, is_owner=is_owner)


# ---------------- registration ----------------
@bp.post("/events/<int:event_id>/register")
@login_required
def register_event(event_id):
    reg, error = services.register_user(event_id, current_user)
    if error:
        flash(error, "error")
    elif reg.status == "confirmed":
        flash("You are registered! Your ticket code is " + reg.ticket_code + ".", "ok")
    else:
        flash("The event is full, so you were added to the waitlist.", "ok")
    return redirect(url_for("views.event_detail", event_id=event_id))


@bp.post("/events/<int:event_id>/unregister")
@login_required
def unregister_event(event_id):
    reg = Registration.query.filter_by(event_id=event_id, user_id=current_user.id).first()
    if reg is None or reg.status == "cancelled":
        flash("You are not registered for this event.", "error")
    else:
        services.cancel_registration(reg)
        flash("Your registration was cancelled.", "ok")
    return redirect(url_for("views.event_detail", event_id=event_id))


@bp.get("/my/tickets")
@login_required
def my_tickets():
    rows = (
        db.session.query(Registration, Event)
        .join(Event, Event.id == Registration.event_id)
        .filter(Registration.user_id == current_user.id, Registration.status != "cancelled")
        .order_by(Event.starts_at.desc())
        .all()
    )
    return render_template("my_tickets.html", rows=rows)


# ---------------- organizer ----------------
@bp.route("/events/new", methods=["GET", "POST"])
@login_required
def new_event():
    values, errors = {"category": "Technical", "price": "0"}, {}
    if request.method == "POST":
        values = {k: request.form.get(k, "") for k in EVENT_FIELDS}
        data, errors = clean_event(request.form, creating=True)
        if not errors:
            event = Event(organizer_id=current_user.id, **data)
            db.session.add(event)
            db.session.commit()
            flash("Event created.", "ok")
            return redirect(url_for("views.event_detail", event_id=event.id))
    return render_template("event_form.html", event=None, values=values, errors=errors,
                           categories=CATEGORIES), (400 if errors else 200)


@bp.route("/events/<int:event_id>/edit", methods=["GET", "POST"])
@login_required
def edit_event(event_id):
    event = owner_event(event_id)
    errors = {}
    if request.method == "POST":
        values = {k: request.form.get(k, "") for k in EVENT_FIELDS}
        data, errors = clean_event(request.form, creating=False)
        if not errors:
            confirmed = services.confirmed_count(event.id)
            if data["capacity"] < confirmed:
                errors["capacity"] = "Capacity cannot be lower than the %d confirmed registrations" % confirmed
        if not errors:
            for key, value in data.items():
                setattr(event, key, value)
            services.promote_waitlist(event)  # capacity may have increased
            db.session.commit()
            flash("Event updated.", "ok")
            return redirect(url_for("views.event_detail", event_id=event.id))
    else:
        values = {
            "title": event.title, "description": event.description, "category": event.category,
            "venue": event.venue, "capacity": str(event.capacity), "price": str(event.price),
            "starts_at": event.starts_at.strftime("%Y-%m-%dT%H:%M"),
            "ends_at": event.ends_at.strftime("%Y-%m-%dT%H:%M") if event.ends_at else "",
        }
    return render_template("event_form.html", event=event, values=values, errors=errors,
                           categories=CATEGORIES), (400 if errors else 200)


@bp.route("/events/<int:event_id>/cancel", methods=["GET", "POST"])
@login_required
def cancel_event(event_id):
    event = owner_event(event_id)
    if request.method == "POST":
        event.status = "cancelled"
        db.session.commit()
        flash("Event cancelled. Registered attendees will see the cancellation on the event page.", "ok")
        return redirect(url_for("views.event_detail", event_id=event.id))
    return render_template("confirm.html", title="Cancel this event?", subject=event.title,
                           message="Registrations stay on record, but nobody can register anymore.",
                           button="Yes, cancel event", back=url_for("views.event_detail", event_id=event.id))


@bp.route("/events/<int:event_id>/delete", methods=["GET", "POST"])
@login_required
def delete_event(event_id):
    event = owner_event(event_id)
    if request.method == "POST":
        db.session.delete(event)
        db.session.commit()
        flash("Event deleted.", "ok")
        return redirect(url_for("views.my_events"))
    return render_template("confirm.html", title="Delete this event?", subject=event.title,
                           message="The event and all its registrations will be removed permanently.",
                           button="Yes, delete", back=url_for("views.event_detail", event_id=event.id))


@bp.get("/my/events")
@login_required
def my_events():
    events = Event.query.filter_by(organizer_id=current_user.id).order_by(Event.starts_at.desc()).all()
    cnt = services.counts([e.id for e in events])
    total_confirmed = sum(c["confirmed"] for c in cnt.values())
    total_waiting = sum(c["waitlisted"] for c in cnt.values())
    upcoming = sum(1 for e in events if e.is_open)
    capacity = sum(e.capacity for e in events)
    fill = round(100 * total_confirmed / capacity) if capacity else 0

    bars = []
    for e in events[:8]:
        c = cnt[e.id]["confirmed"]
        label = e.title if len(e.title) <= 22 else e.title[:21] + "\u2026"
        bars.append({"label": label, "text": "%d/%d" % (c, e.capacity), "pct": min(round(100 * c / e.capacity), 100)})
    return render_template("my_events.html", events=events, cnt=cnt, bars=bars, upcoming=upcoming,
                           total_confirmed=total_confirmed, total_waiting=total_waiting, fill=fill)


@bp.get("/events/<int:event_id>/attendees")
@login_required
def attendees(event_id):
    event = owner_event(event_id)
    regs = (
        db.session.query(Registration)
        .filter(Registration.event_id == event.id, Registration.status != "cancelled")
        .order_by(Registration.status, Registration.created_at)
        .all()
    )
    confirmed = [r for r in regs if r.status == "confirmed"]
    return render_template("attendees.html", event=event, regs=regs, confirmed=len(confirmed),
                           checked_in=sum(1 for r in confirmed if r.checked_in),
                           waiting=len(regs) - len(confirmed))


@bp.post("/events/<int:event_id>/attendees/<int:reg_id>/checkin")
@login_required
def toggle_checkin(event_id, reg_id):
    event = owner_event(event_id)
    reg = db.session.get(Registration, reg_id)
    if reg is None or reg.event_id != event.id or reg.status != "confirmed":
        abort(404, description="Registration not found")
    reg.checked_in = not reg.checked_in
    db.session.commit()
    return redirect(url_for("views.attendees", event_id=event.id))


def _csv_safe(value):
    value = "" if value is None else str(value)
    return "'" + value if value[:1] in ("=", "+", "-", "@") else value


@bp.get("/events/<int:event_id>/attendees.csv")
@login_required
def attendees_csv(event_id):
    event = owner_event(event_id)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["ticket_code", "name", "email", "status", "checked_in", "registered_at"])
    regs = Registration.query.filter(Registration.event_id == event.id, Registration.status != "cancelled") \
        .order_by(Registration.id).all()
    for r in regs:
        w.writerow([r.ticket_code, _csv_safe(r.user.name), _csv_safe(r.user.email), r.status,
                    "yes" if r.checked_in else "no", r.created_at.isoformat()])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=attendees-%d.csv" % event.id})
