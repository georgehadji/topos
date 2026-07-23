"""Slice 0.3: the app boots and /healthz responds. No DB needed for this one."""

from fastapi.testclient import TestClient

from topos.interfaces.http.app import app


def test_healthz_ok() -> None:
    with TestClient(app) as client:
        resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}
