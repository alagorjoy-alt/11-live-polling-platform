"""Happy path + the important failure paths for the polling API."""
import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "test.db"))
    monkeypatch.delenv("ENFORCE_IP_LIMIT", raising=False)
    # `with` keeps one event loop alive so WebSocket tests can share it with HTTP calls
    with TestClient(app) as c:
        yield c


def make_poll(client, **overrides):
    payload = {"question": "Best language?", "options": ["Python", "Go", "Rust"]}
    payload.update(overrides)
    res = client.post("/api/polls", json=payload)
    assert res.status_code == 201, res.text
    return res.json()


def new_voter(client):
    """A second browser: same app, separate cookie jar."""
    return TestClient(client.app)


# ---------- happy path ----------
def test_create_vote_and_results(client):
    poll = make_poll(client)
    assert poll["total_votes"] == 0 and len(poll["options"]) == 3
    python_id = poll["options"][0]["id"]

    res = client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": python_id})
    assert res.status_code == 201
    assert res.json()["total_votes"] == 1

    got = client.get(f"/api/polls/{poll['id']}").json()
    assert got["options"][0]["votes"] == 1
    assert got["options"][0]["percent"] == 100.0
    assert got["my_vote"] == python_id
    assert "admin_token" not in got  # never leaked after creation


def test_different_voters_can_both_vote(client):
    poll = make_poll(client)
    opt = poll["options"][1]["id"]
    assert client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": opt}).status_code == 201
    other = new_voter(client)
    assert other.post(f"/api/polls/{poll['id']}/vote", json={"option_id": opt}).status_code == 201
    assert client.get(f"/api/polls/{poll['id']}").json()["total_votes"] == 2


def test_websocket_receives_live_update(client):
    poll = make_poll(client)
    opt = poll["options"][2]["id"]
    with client.websocket_connect(f"/ws/polls/{poll['id']}") as ws:
        assert ws.receive_json()["total_votes"] == 0  # snapshot on connect
        client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": opt})
        msg = ws.receive_json()
        assert msg["type"] == "results" and msg["total_votes"] == 1


# ---------- major failure path: duplicate voting ----------
def test_duplicate_vote_is_rejected(client):
    poll = make_poll(client)
    a, b = poll["options"][0]["id"], poll["options"][1]["id"]
    assert client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": a}).status_code == 201
    again = client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": b})
    assert again.status_code == 409
    assert client.get(f"/api/polls/{poll['id']}").json()["total_votes"] == 1


def test_ip_limit_blocks_second_browser(client, monkeypatch):
    monkeypatch.setenv("ENFORCE_IP_LIMIT", "true")
    poll = make_poll(client)
    opt = poll["options"][0]["id"]
    assert client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": opt}).status_code == 201
    other = new_voter(client)  # fresh cookie, same IP
    assert other.post(f"/api/polls/{poll['id']}/vote", json={"option_id": opt}).status_code == 409


# ---------- other edge cases ----------
def test_vote_on_closed_poll(client):
    poll = make_poll(client)
    closed = client.post(f"/api/polls/{poll['id']}/close", headers={"X-Admin-Token": poll["admin_token"]})
    assert closed.status_code == 200
    res = client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": poll["options"][0]["id"]})
    assert res.status_code == 410


def test_close_requires_admin_token(client):
    poll = make_poll(client)
    assert client.post(f"/api/polls/{poll['id']}/close").status_code == 403
    bad = client.post(f"/api/polls/{poll['id']}/close", headers={"X-Admin-Token": "nope"})
    assert bad.status_code == 403
    assert client.get(f"/api/polls/{poll['id']}").json()["is_closed"] is False


def test_option_from_another_poll_is_rejected(client):
    p1, p2 = make_poll(client), make_poll(client, question="Other poll?")
    res = client.post(f"/api/polls/{p1['id']}/vote", json={"option_id": p2["options"][0]["id"]})
    assert res.status_code == 400


def test_unknown_poll(client):
    assert client.get("/api/polls/nope").status_code == 404
    assert client.post("/api/polls/nope/vote", json={"option_id": 1}).status_code == 404
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws/polls/nope"):
            pass


@pytest.mark.parametrize("payload", [
    {"question": "Only one?", "options": ["Solo"]},
    {"question": "Dupes?", "options": ["A", "a"]},
    {"question": "Blank?", "options": ["A", "   "]},
    {"question": "", "options": ["A", "B"]},
    {"question": "Too many?", "options": [str(i) for i in range(11)]},
    {"question": "Bad time?", "options": ["A", "B"], "duration_minutes": 0},
])
def test_poll_validation(client, payload):
    assert client.post("/api/polls", json=payload).status_code == 422


def test_bad_vote_body(client):
    poll = make_poll(client)
    assert client.post(f"/api/polls/{poll['id']}/vote", json={"option_id": "x"}).status_code == 422


def test_health_and_metrics(client):
    assert client.get("/health").json() == {"status": "ok"}
    make_poll(client)
    assert client.get("/api/metrics").json()["polls_total"] == 1
