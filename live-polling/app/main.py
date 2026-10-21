"""Live Polling Platform: FastAPI app (REST + WebSocket + static frontend)."""
import hashlib
import logging
import re
import secrets
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import db, init_db
from .manager import manager
from .polls import (close_poll, create_poll, get_poll_row, get_results, list_polls,
                    poll_is_closed, serialize_poll)
from .schemas import PollCreate, VoteIn
from .voting import (DuplicateVote, InvalidOption, PollClosed, PollNotFound, cast_vote)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("polling")

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"
VOTER_COOKIE = "voter_id"
VOTER_ID_RE = re.compile(r"^[A-Za-z0-9_-]{16,64}$")

# Simple in-process counters exposed at /api/metrics
metrics = {"polls_created": 0, "votes_accepted": 0, "duplicates_blocked": 0, "closed_rejections": 0}


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info("database ready at %s", settings.database_path)
    yield


app = FastAPI(title="Live Polling Platform", version="1.0.0", lifespan=lifespan)


# ---------- helpers ----------
def _voter_id(request: Request) -> tuple[str, bool]:
    """Return (voter_id, is_new). Cookies that look wrong are replaced."""
    existing = request.cookies.get(VOTER_COOKIE)
    if existing and VOTER_ID_RE.match(existing):
        return existing, False
    return secrets.token_urlsafe(24), True


def _client_ip(request: Request) -> str:
    if settings.trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _ip_hash(request: Request) -> str | None:
    if not settings.enforce_ip_limit:
        return None
    raw = f"{settings.hash_salt}:{_client_ip(request)}".encode()
    return hashlib.sha256(raw).hexdigest()


def _results_message(conn, poll_id: str, row) -> dict:
    return {"type": "results", "poll_id": poll_id, "is_closed": poll_is_closed(row),
            **get_results(conn, poll_id)}


# ---------- REST API ----------
@app.post("/api/polls", status_code=201)
async def api_create_poll(body: PollCreate):
    with db() as conn:
        poll_id, admin_token = create_poll(conn, body.question, body.options, body.duration_minutes)
        row = get_poll_row(conn, poll_id)
        data = serialize_poll(conn, row)
    metrics["polls_created"] += 1
    log.info("poll created id=%s options=%d", poll_id, len(body.options))
    # The admin token is shown once; the creator needs it to close the poll.
    return {**data, "admin_token": admin_token}


@app.get("/api/polls")
async def api_list_polls():
    with db() as conn:
        return list_polls(conn)


@app.get("/api/polls/{poll_id}")
async def api_get_poll(poll_id: str, request: Request):
    voter_id = request.cookies.get(VOTER_COOKIE)
    with db() as conn:
        row = get_poll_row(conn, poll_id)
        if row is None:
            raise HTTPException(404, "Poll not found")
        return serialize_poll(conn, row, voter_id)


@app.post("/api/polls/{poll_id}/vote", status_code=201)
async def api_vote(poll_id: str, body: VoteIn, request: Request, response: Response):
    voter_id, is_new = _voter_id(request)
    try:
        with db() as conn:
            cast_vote(conn, poll_id, body.option_id, voter_id, _ip_hash(request))
            row = get_poll_row(conn, poll_id)
            message = _results_message(conn, poll_id, row)
    except PollNotFound:
        raise HTTPException(404, "Poll not found")
    except PollClosed:
        metrics["closed_rejections"] += 1
        raise HTTPException(410, "This poll is closed")
    except InvalidOption:
        raise HTTPException(400, "That option does not belong to this poll")
    except DuplicateVote:
        metrics["duplicates_blocked"] += 1
        log.info("duplicate vote blocked poll=%s", poll_id)
        raise HTTPException(409, "You have already voted on this poll")

    if is_new:
        response.set_cookie(VOTER_COOKIE, voter_id, max_age=60 * 60 * 24 * 365,
                            httponly=True, samesite="lax", secure=settings.cookie_secure)
    metrics["votes_accepted"] += 1
    await manager.broadcast(poll_id, message)  # push to every open results page
    return {"message": "Vote recorded", "my_vote": body.option_id, **get_results_payload(message)}


def get_results_payload(message: dict) -> dict:
    return {k: message[k] for k in ("is_closed", "total_votes", "options")}


@app.post("/api/polls/{poll_id}/close")
async def api_close_poll(poll_id: str, x_admin_token: str | None = Header(default=None)):
    with db() as conn:
        row = get_poll_row(conn, poll_id)
        if row is None:
            raise HTTPException(404, "Poll not found")
        if not x_admin_token or not secrets.compare_digest(x_admin_token, row["admin_token"]):
            raise HTTPException(403, "Invalid admin token")
        close_poll(conn, poll_id)
        row = get_poll_row(conn, poll_id)
        message = _results_message(conn, poll_id, row)
    await manager.broadcast(poll_id, message)
    return {"message": "Poll closed", **get_results_payload(message)}


@app.get("/api/metrics")
async def api_metrics():
    with db() as conn:
        polls = conn.execute("SELECT COUNT(*) FROM polls").fetchone()[0]
        votes = conn.execute("SELECT COUNT(*) FROM votes").fetchone()[0]
    return {"polls_total": polls, "votes_total": votes,
            "websocket_connections": manager.active_connections, **metrics}


@app.get("/health")
async def health():
    with db() as conn:
        conn.execute("SELECT 1").fetchone()
    return {"status": "ok"}


# ---------- WebSocket ----------
@app.websocket("/ws/polls/{poll_id}")
async def ws_poll(ws: WebSocket, poll_id: str):
    with db() as conn:
        row = get_poll_row(conn, poll_id)
        snapshot = _results_message(conn, poll_id, row) if row else None
    if snapshot is None:
        await ws.close(code=4404)
        return
    await manager.connect(poll_id, ws)
    try:
        await ws.send_json(snapshot)  # current state immediately on connect
        while True:
            text = await ws.receive_text()
            if text == "ping":  # client heartbeat keeps idle proxies from closing the socket
                await ws.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(poll_id, ws)


# ---------- Frontend ----------
@app.get("/", include_in_schema=False)
async def index_page():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/p/{poll_id}", include_in_schema=False)
async def poll_page(poll_id: str):
    return FileResponse(STATIC_DIR / "poll.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
