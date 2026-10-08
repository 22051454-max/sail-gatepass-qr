import secrets
from datetime import datetime, timedelta, timezone

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

ROLES = ("admin", "security", "staff")


def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    role = db.Column(db.String(16), nullable=False, default="staff")
    password_hash = db.Column(db.String(256), nullable=False)
    active = db.Column(db.Boolean, default=True)

    def set_password(self, pw):
        self.password_hash = generate_password_hash(pw)

    def check_password(self, pw):
        return check_password_hash(self.password_hash, pw)


class GatePass(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pass_no = db.Column(db.String(20), unique=True, nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=False, default=lambda: secrets.token_urlsafe(24))
    visitor_name = db.Column(db.String(120), nullable=False)
    visitor_phone = db.Column(db.String(20))
    id_proof = db.Column(db.String(60))
    company = db.Column(db.String(120))
    purpose = db.Column(db.String(200), nullable=False)
    department = db.Column(db.String(80), nullable=False)
    vehicle_no = db.Column(db.String(20))
    gate = db.Column(db.String(30), default="Main Gate")
    status = db.Column(db.String(16), default="issued")  # issued, inside, exited, revoked
    created_at = db.Column(db.DateTime, default=utcnow)
    valid_until = db.Column(db.DateTime, nullable=False)
    created_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    created_by = db.relationship("User")
    materials = db.relationship("MaterialEntry", backref="gate_pass", cascade="all, delete-orphan")
    scans = db.relationship("ScanLog", backref="gate_pass", cascade="all, delete-orphan",
                            order_by="ScanLog.scanned_at")

    @property
    def is_expired(self):
        return utcnow() > self.valid_until

    @staticmethod
    def next_pass_no():
        today = utcnow().strftime("%Y%m%d")
        count = GatePass.query.filter(GatePass.pass_no.like(f"GP{today}%")).count()
        return f"GP{today}{count + 1:04d}"

    @classmethod
    def issue(cls, hours, **fields):
        return cls(pass_no=cls.next_pass_no(), valid_until=utcnow() + timedelta(hours=hours), **fields)


class MaterialEntry(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gate_pass_id = db.Column(db.Integer, db.ForeignKey("gate_pass.id"), nullable=False)
    description = db.Column(db.String(200), nullable=False)
    quantity = db.Column(db.Float, nullable=False)
    unit = db.Column(db.String(20), default="nos")
    direction = db.Column(db.String(8), default="in")  # in / out
    returnable = db.Column(db.Boolean, default=False)
    verified = db.Column(db.Boolean, default=False)


class ScanLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    gate_pass_id = db.Column(db.Integer, db.ForeignKey("gate_pass.id"), nullable=False)
    action = db.Column(db.String(16), nullable=False)  # entry, exit, rejected
    note = db.Column(db.String(200))
    gate = db.Column(db.String(30))
    scanned_at = db.Column(db.DateTime, default=utcnow)
    scanned_by_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    scanned_by = db.relationship("User")


def seed_demo_data():
    if User.query.first():
        return
    demo_users = [
        ("admin", "Plant Admin", "admin", "admin123"),
        ("guard", "Gate Security Officer", "security", "guard123"),
        ("staff", "Stores Department Staff", "staff", "staff123"),
    ]
    for username, name, role, pw in demo_users:
        u = User(username=username, full_name=name, role=role)
        u.set_password(pw)
        db.session.add(u)
    db.session.commit()
    staff = User.query.filter_by(username="staff").first()
    samples = [
        ("Ravi Kumar", "Bharat Engineering Works", "Conveyor belt maintenance", "Mechanical", "JH01AB1234",
         [("Welding machine", 1, "nos", "in", True), ("Spare rollers", 12, "nos", "in", False)]),
        ("Anita Singh", "Eastern Supplies", "Delivery of safety gear", "Stores", "JH05CD5678",
         [("Safety helmets", 50, "nos", "in", False)]),
        ("Mohit Verma", "Self", "Interview", "HR", None, []),
    ]
    for name, company, purpose, dept, vehicle, mats in samples:
        gp = GatePass.issue(12, visitor_name=name, company=company, purpose=purpose,
                            department=dept, vehicle_no=vehicle, created_by=staff,
                            visitor_phone="98xxxxxx10", id_proof="Aadhaar (masked)")
        db.session.add(gp)
        db.session.flush()
        for desc, qty, unit, direction, ret in mats:
            db.session.add(MaterialEntry(gate_pass=gp, description=desc, quantity=qty, unit=unit,
                                         direction=direction, returnable=ret))
    db.session.commit()
