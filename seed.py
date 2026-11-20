"""Optional demo data. Enabled only when the environment variable SEED_DEMO=1 is set."""
from datetime import timedelta

from .models import Event, Registration, User, db, now_local


def seed_demo():
    if User.query.count() > 0:
        return
    org = User(name="Demo Organizer", email="demo@eventhub.com")
    org.set_password("demo12345")
    db.session.add(org)
    db.session.flush()

    base = now_local().replace(hour=10, minute=0, second=0, microsecond=0)
    samples = [
        ("AWS Cloud Workshop", "Technical", "Seminar Hall A", 3, 60, 0, "Hands-on session: deploy a Python app on AWS Elastic Beanstalk."),
        ("Inter-College Hackathon", "Technical", "Computer Lab 2", 7, 3, 199, "24-hour coding challenge. Teams of up to 4. Small capacity to demo the waitlist."),
        ("Annual Cultural Fest", "Cultural", "Main Auditorium", 12, 500, 100, "Music, dance and drama performances by students."),
        ("Placement Preparation Talk", "Seminar", "Auditorium B", 5, 120, 0, "Resume tips and mock interview strategies by alumni."),
        ("Football Tournament", "Sports", "College Ground", 9, 80, 50, "5-a-side knockout tournament."),
        ("Photography Walk", "Social", "Cubbon Park Gate", 2, 25, 0, "Morning walk and photo session for beginners."),
    ]
    for title, cat, venue, days, cap, price, desc in samples:
        start = base + timedelta(days=days)
        db.session.add(Event(
            organizer_id=org.id, title=title, category=cat, venue=venue, starts_at=start,
            ends_at=start + timedelta(hours=3), capacity=cap, price=price, description=desc,
        ))
    db.session.commit()
