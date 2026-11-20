from flask import Blueprint, abort, jsonify, request

from . import services
from .models import Event, db, now_local, utcnow

bp = Blueprint("api", __name__, url_prefix="/api")


def event_dict(event, cnt):
    return {
        "id": event.id,
        "title": event.title,
        "category": event.category,
        "venue": event.venue,
        "starts_at": event.starts_at.isoformat(),
        "ends_at": event.ends_at.isoformat() if event.ends_at else None,
        "capacity": event.capacity,
        "confirmed": cnt["confirmed"],
        "seats_left": max(event.capacity - cnt["confirmed"], 0),
        "waitlisted": cnt["waitlisted"],
        "price": event.price,
        "status": event.status,
    }


@bp.get("/health")
def health():
    db.session.execute(db.text("SELECT 1"))
    return jsonify(status="ok", time=utcnow().isoformat() + "Z")


@bp.get("/events")
def list_events():
    q = Event.query.filter(Event.status == "published", db.func.coalesce(Event.ends_at, Event.starts_at) >= now_local())
    category = request.args.get("category")
    if category:
        q = q.filter(Event.category == category)
    events = q.order_by(Event.starts_at).limit(100).all()
    cnt = services.counts([e.id for e in events])
    return jsonify([event_dict(e, cnt[e.id]) for e in events])


@bp.get("/events/<int:event_id>")
def get_event(event_id):
    event = db.session.get(Event, event_id)
    if event is None:
        abort(404, description="Event not found")
    return jsonify(event_dict(event, services.counts([event.id])[event.id]))
