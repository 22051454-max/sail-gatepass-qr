from datetime import timedelta

import pytest

from app import create_app
from app.models import GatePass, db, utcnow


@pytest.fixture
def app(tmp_path):
    return create_app({"TESTING": True, "SQLALCHEMY_DATABASE_URI": f"sqlite:///{tmp_path}/t.db"})


def login(client, user, pw):
    return client.post("/login", data={"username": user, "password": pw})


def test_login_required(app):
    assert app.test_client().get("/").status_code == 302


def test_bad_login(app):
    r = login(app.test_client(), "admin", "nope")
    assert b"Invalid" in r.data


def test_staff_creates_pass_with_materials(app):
    c = app.test_client()
    login(c, "staff", "staff123")
    r = c.post("/passes/new", data={
        "visitor_name": "Test Visitor", "purpose": "Audit", "department": "Stores",
        "mat_desc": ["Laptop"], "mat_qty": ["1"], "mat_unit": ["nos"], "mat_dir": ["in"], "mat_ret": ["0"],
    })
    assert r.status_code == 302
    with app.app_context():
        gp = GatePass.query.filter_by(visitor_name="Test Visitor").one()
        assert gp.materials[0].returnable is True
        assert gp.pass_no.startswith("GP")


def test_staff_cannot_scan(app):
    c = app.test_client()
    login(c, "staff", "staff123")
    assert c.post("/api/verify", json={"token": "x"}).status_code == 403


def test_entry_exit_and_reuse(app):
    c = app.test_client()
    login(c, "guard", "guard123")
    with app.app_context():
        token = GatePass.query.first().token
    r1 = c.post("/api/verify", json={"token": token}).get_json()
    r2 = c.post("/api/verify", json={"token": token}).get_json()
    r3 = c.post("/api/verify", json={"token": token})
    assert (r1["action"], r2["action"]) == ("entry", "exit")
    assert r3.status_code == 422


def test_expired_and_unknown(app):
    c = app.test_client()
    login(c, "guard", "guard123")
    with app.app_context():
        gp = GatePass.query.first()
        gp.valid_until = utcnow() - timedelta(hours=1)
        db.session.commit()
        token = gp.token
    assert "expired" in c.post("/api/verify", json={"token": token}).get_json()["message"]
    assert c.post("/api/verify", json={"token": "bogus"}).status_code == 422


def test_revoked(app):
    c = app.test_client()
    login(c, "admin", "admin123")
    with app.app_context():
        gp = GatePass.query.first()
        pass_no, token = gp.pass_no, gp.token
    c.post(f"/admin/passes/{pass_no}/revoke")
    assert c.post("/api/verify", json={"token": token}).get_json()["message"] == "Pass has been revoked"


def test_csv_export_admin_only(app):
    c = app.test_client()
    login(c, "admin", "admin123")
    r = c.get("/admin/export.csv")
    assert r.status_code == 200 and b"pass_no" in r.data
