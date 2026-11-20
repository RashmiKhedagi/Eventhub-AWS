import os
import tempfile

from flask import Flask, jsonify, redirect, render_template, request, url_for
from flask_login import LoginManager
from werkzeug.exceptions import HTTPException

from .models import User, db
from .security import csrf_protect, csrf_token

login_manager = LoginManager()


def _default_db_url():
    base = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
    folder = base if os.access(base, os.W_OK) else tempfile.gettempdir()
    return "sqlite:///" + os.path.join(folder, "eventhub.db")


def create_app(config=None):
    app = Flask(__name__)

    db_url = os.environ.get("DATABASE_URL") or _default_db_url()
    if db_url.startswith("postgres://"):
        db_url = db_url.replace("postgres://", "postgresql://", 1)

    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=db_url,
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("COOKIE_SECURE", "0") == "1",
        MAX_CONTENT_LENGTH=64 * 1024,
    )
    if config:
        app.config.update(config)

    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        if request.path.startswith("/api"):
            return jsonify(error="Authentication required"), 401
        return redirect(url_for("auth.login", next=request.path))

    app.before_request(csrf_protect)
    app.jinja_env.globals["csrf_token"] = csrf_token

    # ---- template filters ----
    app.jinja_env.filters["fmt_dt"] = lambda d: d.strftime("%a, %d %b %Y, %I:%M %p") if d else ""
    app.jinja_env.filters["fmt_input"] = lambda d: d.strftime("%Y-%m-%dT%H:%M") if d else ""
    app.jinja_env.filters["money"] = lambda p: "Free" if not p else "\u20b9{:,}".format(p)

    @app.after_request
    def security_headers(resp):
        resp.headers["X-Content-Type-Options"] = "nosniff"
        resp.headers["X-Frame-Options"] = "DENY"
        resp.headers["Referrer-Policy"] = "same-origin"
        resp.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'"
        return resp

    @app.errorhandler(HTTPException)
    def http_error(err):
        if request.path.startswith("/api"):
            return jsonify(error=err.description or err.name), err.code
        return render_template("error.html", err=err), err.code

    from .api import bp as api_bp
    from .auth import bp as auth_bp
    from .views import bp as views_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(views_bp)

    with app.app_context():
        db.create_all()
        if os.environ.get("SEED_DEMO") == "1":
            from .seed import seed_demo
            seed_demo()

    return app
