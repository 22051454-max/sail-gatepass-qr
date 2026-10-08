import csv
import io

from flask import Blueprint, Response, abort, flash, redirect, render_template, request, url_for

from .auth import login_required
from .models import ROLES, GatePass, ScanLog, User, db

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/users", methods=["GET", "POST"])
@login_required("admin")
def users():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        role = request.form.get("role", "staff")
        pw = request.form.get("password", "")
        if not username or role not in ROLES or len(pw) < 6:
            flash("Username, a valid role and a 6+ character password are required", "error")
        elif User.query.filter_by(username=username).first():
            flash("Username already exists", "error")
        else:
            u = User(username=username, full_name=request.form.get("full_name") or username, role=role)
            u.set_password(pw)
            db.session.add(u)
            db.session.commit()
            flash(f"User {username} created", "success")
        return redirect(url_for("admin.users"))
    return render_template("users.html", users=User.query.order_by(User.id).all(), roles=ROLES)


@bp.route("/users/<int:uid>/toggle", methods=["POST"])
@login_required("admin")
def toggle_user(uid):
    u = db.session.get(User, uid) or abort(404)
    if u.username != "admin":
        u.active = not u.active
        db.session.commit()
    return redirect(url_for("admin.users"))


@bp.route("/passes/<pass_no>/revoke", methods=["POST"])
@login_required("admin")
def revoke(pass_no):
    gp = GatePass.query.filter_by(pass_no=pass_no).first_or_404()
    gp.status = "revoked"
    db.session.commit()
    flash(f"{pass_no} revoked", "success")
    return redirect(url_for("passes.view_pass", pass_no=pass_no))


@bp.route("/logs")
@login_required("admin", "security")
def logs():
    return render_template("logs.html", logs=ScanLog.query.order_by(ScanLog.scanned_at.desc()).limit(200).all())


@bp.route("/export.csv")
@login_required("admin")
def export_csv():
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["pass_no", "visitor", "company", "department", "purpose", "vehicle", "status", "created", "valid_until"])
    for gp in GatePass.query.order_by(GatePass.created_at).all():
        w.writerow([gp.pass_no, gp.visitor_name, gp.company, gp.department, gp.purpose,
                    gp.vehicle_no, gp.status, gp.created_at, gp.valid_until])
    return Response(buf.getvalue(), mimetype="text/csv",
                    headers={"Content-Disposition": "attachment; filename=gate_passes.csv"})
