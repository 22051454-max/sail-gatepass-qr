import base64
import io

import qrcode
from flask import Blueprint, abort, current_app, flash, g, jsonify, redirect, render_template, request, url_for

from .auth import login_required
from .models import GatePass, MaterialEntry, ScanLog, db, utcnow

bp = Blueprint("passes", __name__)


def qr_data_uri(text):
    img = qrcode.make(text, box_size=8, border=2)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


@bp.route("/")
@login_required()
def dashboard():
    q = GatePass.query
    if g.user.role == "staff":
        q = q.filter_by(created_by_id=g.user.id)
    passes = q.order_by(GatePass.created_at.desc()).limit(50).all()
    today = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    stats = {
        "today": GatePass.query.filter(GatePass.created_at >= today).count(),
        "inside": GatePass.query.filter_by(status="inside").count(),
        "exited": GatePass.query.filter_by(status="exited").count(),
        "materials_pending": MaterialEntry.query.filter_by(verified=False).count(),
    }
    return render_template("dashboard.html", passes=passes, stats=stats)


@bp.route("/passes/new", methods=["GET", "POST"])
@login_required("admin", "staff")
def new_pass():
    if request.method == "POST":
        f = request.form
        required = ["visitor_name", "purpose", "department"]
        if any(not f.get(k, "").strip() for k in required):
            flash("Visitor name, purpose and department are required", "error")
            return render_template("new_pass.html", form=f), 400
        hours = min(max(int(f.get("validity_hours") or current_app.config["PASS_VALIDITY_HOURS"]), 1), 72)
        gp = GatePass.issue(
            hours,
            visitor_name=f["visitor_name"].strip(), visitor_phone=f.get("visitor_phone", "").strip(),
            id_proof=f.get("id_proof", "").strip(), company=f.get("company", "").strip(),
            purpose=f["purpose"].strip(), department=f["department"].strip(),
            vehicle_no=f.get("vehicle_no", "").strip().upper() or None,
            gate=f.get("gate") or "Main Gate", created_by=g.user,
        )
        db.session.add(gp)
        descs, qtys = f.getlist("mat_desc"), f.getlist("mat_qty")
        units, dirs, rets = f.getlist("mat_unit"), f.getlist("mat_dir"), f.getlist("mat_ret")
        for i, desc in enumerate(descs):
            if desc.strip():
                try:
                    qty = float(qtys[i])
                except (ValueError, IndexError):
                    qty = 1
                db.session.add(MaterialEntry(
                    gate_pass=gp, description=desc.strip(), quantity=qty,
                    unit=(units[i] if i < len(units) else "nos") or "nos",
                    direction=dirs[i] if i < len(dirs) and dirs[i] in ("in", "out") else "in",
                    returnable=str(i) in rets,
                ))
        db.session.commit()
        flash(f"Gate pass {gp.pass_no} issued", "success")
        return redirect(url_for("passes.view_pass", pass_no=gp.pass_no))
    return render_template("new_pass.html", form={})


@bp.route("/passes/<pass_no>")
@login_required()
def view_pass(pass_no):
    gp = GatePass.query.filter_by(pass_no=pass_no).first_or_404()
    if g.user.role == "staff" and gp.created_by_id != g.user.id:
        abort(403)
    return render_template("pass.html", gp=gp, qr=qr_data_uri(gp.token))


def evaluate_scan(gp, gate):
    """Return (action, ok, message) for a scan without mutating."""
    if gp is None:
        return "rejected", False, "Unknown QR code"
    if gp.status == "revoked":
        return "rejected", False, "Pass has been revoked"
    if gp.status == "issued":
        if gp.is_expired:
            return "rejected", False, "Pass expired before entry"
        return "entry", True, "Entry allowed"
    if gp.status == "inside":
        return "exit", True, "Exit recorded"
    return "rejected", False, "Pass already used (visitor has exited)"


@bp.route("/scan")
@login_required("admin", "security")
def scan_page():
    return render_template("scan.html")


@bp.route("/api/verify", methods=["POST"])
@login_required("admin", "security")
def verify():
    data = request.get_json(silent=True) or request.form
    token = (data.get("token") or "").strip()
    gate = data.get("gate") or "Main Gate"
    commit = str(data.get("commit", "true")).lower() != "false"
    gp = GatePass.query.filter_by(token=token).first() if token else None
    action, ok, message = evaluate_scan(gp, gate)
    if gp is not None and commit:
        if action == "entry":
            gp.status = "inside"
        elif action == "exit":
            gp.status = "exited"
        db.session.add(ScanLog(gate_pass=gp, action=action, note=message, gate=gate, scanned_by=g.user))
        db.session.commit()
    payload = {"ok": ok, "action": action, "message": message}
    if gp is not None:
        payload["pass"] = {
            "pass_no": gp.pass_no, "visitor_name": gp.visitor_name, "company": gp.company,
            "department": gp.department, "vehicle_no": gp.vehicle_no, "status": gp.status,
            "valid_until": gp.valid_until.isoformat(timespec="minutes"),
            "materials": [
                {"id": m.id, "description": m.description, "quantity": m.quantity, "unit": m.unit,
                 "direction": m.direction, "returnable": m.returnable, "verified": m.verified}
                for m in gp.materials
            ],
        }
    return jsonify(payload), (200 if ok else 422)


@bp.route("/api/materials/<int:mid>/verify", methods=["POST"])
@login_required("admin", "security")
def verify_material(mid):
    m = db.session.get(MaterialEntry, mid) or abort(404)
    m.verified = True
    db.session.commit()
    return jsonify({"ok": True, "id": m.id})
