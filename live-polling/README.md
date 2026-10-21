# Show of Hands: Live Polling Platform

Create a poll, share the link, and watch votes arrive in real time. Each browser can vote once.

**Stack:** FastAPI + WebSockets, SQLite, plain HTML/JS with Chart.js.

## Features
- Create polls with 2 to 10 options and an optional voting window (5 min to 7 days)
- Live results over WebSockets (automatic reconnect and heartbeat)
- Duplicate-vote prevention (cookie + database constraint, optional IP limit)
- Poll owner can close a poll with a private admin token
- Validation and clear error states (400, 403, 404, 409, 410, 422)
- `/health` and `/api/metrics` for basic monitoring

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
cp .env.example .env                                    # optional; defaults work locally
python seed.py                                          # optional sample polls
uvicorn app.main:app --reload
```
Open http://localhost:8000. Interactive API docs: http://localhost:8000/docs

Run the tests: `pytest -q`

To watch the chart move, open a poll, then run `python demo_votes.py POLL_ID --count 15`.

## Environment variables
| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_PATH` | `polling.db` | SQLite file location |
| `HASH_SALT` | `dev-salt-change-me` | Salt for hashing IPs (use a random value in production) |
| `ENFORCE_IP_LIMIT` | `false` | Also allow only one vote per IP per poll |
| `TRUST_PROXY` | `false` | Read client IP from `X-Forwarded-For` (true on Render/Railway/Fly) |
| `COOKIE_SECURE` | `false` | Send the voter cookie over HTTPS only (true in production) |

Note: the app does not load `.env` by itself. Export the variables in your shell, or use
`uvicorn app.main:app --env-file .env`.

## API
| Method | Path | Description |
|---|---|---|
| POST | `/api/polls` | Create a poll. Returns the poll plus a one-time `admin_token` |
| GET | `/api/polls` | List recent polls |
| GET | `/api/polls/{id}` | Poll, live results, and `my_vote` for this browser |
| POST | `/api/polls/{id}/vote` | Body `{"option_id": 1}`. 201, or 400/404/409/410 |
| POST | `/api/polls/{id}/close` | Header `X-Admin-Token`. 200, or 403/404 |
| GET | `/api/metrics` | Counters and open WebSocket count |
| GET | `/health` | Liveness check |
| WS | `/ws/polls/{id}` | Sends current results on connect and after every vote or close |

Example:
```bash
curl -X POST localhost:8000/api/polls -H "Content-Type: application/json" \
  -d '{"question":"Lunch?","options":["Pizza","Salad"],"duration_minutes":30}'
```

## Data model
```
polls   (id PK, question, admin_token, created_at, closes_at NULL, is_closed)
options (id PK, poll_id FK, label, position)
votes   (id PK, poll_id FK, option_id FK, voter_id, ip_hash NULL, created_at,
         UNIQUE(poll_id, voter_id),
         UNIQUE(poll_id, ip_hash) WHERE ip_hash IS NOT NULL)
```

## Project layout
```
app/main.py       routes, WebSocket endpoint, static pages
app/voting.py     vote rules (closed? valid option? duplicate?)
app/polls.py      poll queries and result aggregation
app/manager.py    WebSocket rooms and broadcast
app/schemas.py    request validation
app/database.py   schema and SQLite helpers
static/           index.html, poll.html, JS, CSS
tests/            pytest suite
seed.py           sample data
demo_votes.py     fake voters for live demos
```

## Deploy (Render, free tier)
1. Push this folder to GitHub.
2. In Render choose **New > Blueprint** and select the repo (it reads `render.yaml`), or create a Web Service with
   build `pip install -r requirements.txt` and start `uvicorn app.main:app --host 0.0.0.0 --port $PORT`.
3. Set `TRUST_PROXY=true`, `COOKIE_SECURE=true` and a random `HASH_SALT`.
4. Run **one instance only**: WebSocket rooms live in memory.

The free tier has no persistent disk, so SQLite data resets on each deploy or restart. For a demo, run
`python seed.py` after deploy. For durable data, attach a disk and point `DATABASE_PATH` at it, or move to Postgres.

Serve the frontend from this same app. A separately hosted frontend (Vercel/Netlify) would need CORS and
cross-site cookies, which complicates duplicate-vote prevention.

## Trade-offs
- **Cookie-based voter identity** needs no login, but a determined user can clear cookies or use another browser.
  `ENFORCE_IP_LIMIT=true` raises the bar, though people behind one shared network then count as one voter.
- **SQLite** means zero setup and is fine for one server and light traffic.
- **In-memory WebSocket rooms** are simple but limit the app to one process. Scaling out needs Redis pub/sub.
- **Synchronous sqlite calls inside async routes** are fast enough at MVP scale.

## Next improvements
User accounts and per-poll authorization, rate limiting, audit log, Postgres plus Redis pub/sub for multiple
instances, multi-select and named/anonymous modes, CSV export, Prometheus metrics, browser end-to-end tests.
