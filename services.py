"""Business logic: capacity, waitlist promotion, registration rules."""
from .models import Event, Registration, db


def counts(event_ids):
    """{event_id: {'confirmed': n, 'waitlisted': m}} using one grouped query."""
    result = {i: {"confirmed": 0, "waitlisted": 0} for i in event_ids}
    if not event_ids:
        return result
    rows = (
        db.session.query(Registration.event_id, Registration.status, db.func.count(Registration.id))
        .filter(Registration.event_id.in_(event_ids), Registration.status.in_(("confirmed", "waitlisted")))
        .group_by(Registration.event_id, Registration.status)
    )
    for event_id, status, n in rows:
        result[event_id][status] = n
    return result


def confirmed_count(event_id):
    return Registration.query.filter_by(event_id=event_id, status="confirmed").count()


def promote_waitlist(event):
    """Move the oldest waitlisted people into free seats. Returns promoted registrations."""
    free = event.capacity - confirmed_count(event.id)
    if free <= 0:
        return []
    waiting = (
        Registration.query.filter_by(event_id=event.id, status="waitlisted")
        .order_by(Registration.created_at, Registration.id)
        .limit(free)
        .all()
    )
    for reg in waiting:
        reg.status = "confirmed"
    return waiting


def register_user(event_id, user):
    """Register (or waitlist) a user. Returns (registration, error_message)."""
    # Row lock prevents two people taking the last seat at once on PostgreSQL.
    event = Event.query.filter_by(id=event_id).with_for_update().first()
    if event is None:
        return None, "Event not found."
    if not event.is_open:
        return None, "Registration is closed for this event."

    reg = Registration.query.filter_by(event_id=event.id, user_id=user.id).first()
    if reg and reg.status != "cancelled":
        return None, "You are already registered for this event."

    from .models import utcnow

    # Decide the status BEFORE adding a new row, otherwise autoflush would count it as a seat.
    status = "confirmed" if confirmed_count(event.id) < event.capacity else "waitlisted"

    if reg is None:
        reg = Registration(event_id=event.id, user_id=user.id, status=status)
        db.session.add(reg)
    reg.status = status
    reg.created_at = utcnow()
    reg.checked_in = False
    db.session.commit()
    return reg, None


def cancel_registration(reg):
    event = db.session.get(Event, reg.event_id)
    reg.status = "cancelled"
    reg.checked_in = False
    promoted = promote_waitlist(event)
    db.session.commit()
    return promoted
