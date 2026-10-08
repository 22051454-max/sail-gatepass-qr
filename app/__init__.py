"""QR code based Gate Pass Management System (demo recreation)."""
import os

from flask import Flask

from .models import db, seed_demo_data


def create_app(test_config=None):
    app = Flask(__name__, instance_relative_config=True)
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY", "dev-only-change-me"),
        SQLALCHEMY_DATABASE_URI=os.environ.get(
            "DATABASE_URL", "sqlite:///" + os.path.join(app.instance_path, "gatepass.db")
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        PASS_VALIDITY_HOURS=int(os.environ.get("PASS_VALIDITY_HOURS", "12")),
        SEED_DEMO_DATA=os.environ.get("SEED_DEMO_DATA", "1") == "1",
    )
    if test_config:
        app.config.update(test_config)
    os.makedirs(app.instance_path, exist_ok=True)

    db.init_app(app)
    from .auth import bp as auth_bp
    from .passes import bp as passes_bp
    from .admin import bp as admin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(passes_bp)
    app.register_blueprint(admin_bp)

    with app.app_context():
        db.create_all()
        if app.config["SEED_DEMO_DATA"]:
            seed_demo_data()

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        return resp

    return app
