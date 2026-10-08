from functools import wraps

from flask import Blueprint, abort, flash, g, redirect, render_template, request, session, url_for

from .models import User, db

bp = Blueprint("auth", __name__)


@bp.before_app_request
def load_user():
    uid = session.get("uid")
    g.user = db.session.get(User, uid) if uid else None


def login_required(*roles):
    def deco(view):
        @wraps(view)
        def wrapped(*a, **kw):
            if g.user is None:
                return redirect(url_for("auth.login", next=request.path))
            if roles and g.user.role not in roles:
                abort(403)
            return view(*a, **kw)
        return wrapped
    return deco


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user = User.query.filter_by(username=request.form.get("username", "").strip()).first()
        if user and user.active and user.check_password(request.form.get("password", "")):
            session.clear()
            session["uid"] = user.id
            nxt = request.args.get("next", "")
            return redirect(nxt if nxt.startswith("/") and not nxt.startswith("//") else url_for("passes.dashboard"))
        flash("Invalid username or password", "error")
    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))
