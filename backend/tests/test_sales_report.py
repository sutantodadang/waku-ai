"""Monthly sales Excel report endpoint."""
from helpers import register, auth

SPREADSHEET = "spreadsheetml"


def test_report_default_month_returns_xlsx(client):
    tok = register(client)["access_token"]
    r = client.get("/api/reports/sales", headers=auth(tok))
    assert r.status_code == 200, r.text
    assert SPREADSHEET in r.headers["content-type"]
    assert r.content[:2] == b"PK"


def test_report_specific_month(client):
    tok = register(client)["access_token"]
    r = client.get("/api/reports/sales?month=2026-06", headers=auth(tok))
    assert r.status_code == 200, r.text
    assert r.content[:2] == b"PK"


def test_report_bad_month_422(client):
    tok = register(client)["access_token"]
    r = client.get("/api/reports/sales?month=bad", headers=auth(tok))
    assert r.status_code == 422


def test_report_requires_auth(client):
    r = client.get("/api/reports/sales")
    assert r.status_code in (401, 403)
