# Demo script (about 5 minutes)

## 1. Before you start (off-screen)
- Run the app (`uvicorn app.main:app`) and `python seed.py`.
- Open the home page in a normal window and keep an incognito window ready as a second voter.

## 2. Problem and architecture (45 s)
"A poll should update for everyone the moment a vote lands. The browser uses REST for actions and a WebSocket for
live results. FastAPI holds the business rules, SQLite stores polls, options and votes, and Chart.js draws results."

Sketch: Browser <-> REST (create, vote, close) <-> FastAPI <-> SQLite, and FastAPI --WebSocket--> every open results page.

## 3. End-to-end flow (2 min)
1. **Create:** ask "Which feature should we build next?" with 3 options. Show validation (one option, or duplicate options).
2. **Share:** copy the link and open it in the incognito window beside the first window.
3. **Vote:** cast a vote in the incognito window. The chart and total in the first window move without a refresh.
4. **Run the script:** `python demo_votes.py POLL_ID --count 10` and let the audience watch the bars grow.

## 4. The key edge case: duplicate voting (45 s)
- Vote again in the same window: the form is locked and shows your choice. Show the API returning **409** with
  `curl -i -X POST .../vote ...` (reuse the cookie with `-b`).
- Explain the layers: a voter cookie, plus a database `UNIQUE(poll_id, voter_id)` constraint, so even two
  simultaneous requests cannot both succeed. Optional IP limit via `ENFORCE_IP_LIMIT`.

## 5. Closing and monitoring (30 s)
- Click **Close poll** (only the creator's browser has the admin token). Voting stops everywhere; late votes get **410**.
- Show `/api/metrics`: votes accepted, duplicates blocked, open WebSocket connections.

## 6. Decisions, trade-offs, next steps (30 s)
- No-login cookie identity keeps the demo frictionless; the trade-off is that clearing cookies resets identity.
- SQLite and in-memory WebSocket rooms keep it to a single process.
- Tests (`pytest -q`) cover the happy path, duplicate voting, closed polls, admin auth, validation and a WebSocket push.
- Next: accounts and authorization, rate limiting, Postgres + Redis for scaling, analytics and exports.
