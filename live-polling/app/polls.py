"""Poll data access and result aggregation."""
import secrets
import sqlite3
from datetime import datetime, timedelta, timezone


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds")


def create_poll(conn: sqlite3.Connection, question: str, options: list[str],
                duration_minutes: int | None) -> tuple[str, str]:
    poll_id = secrets.token_urlsafe(6)
    admin_token = secrets.token_urlsafe(24)
    now = utcnow()
    closes_at = _iso(now + timedelta(minutes=duration_minutes)) if duration_minutes else None
    conn.execute(
        "INSERT INTO polls (id, question, admin_token, created_at, closes_at) VALUES (?,?,?,?,?)",
        (poll_id, question, admin_token, _iso(now), closes_at),
    )
    conn.executemany(
        "INSERT INTO options (poll_id, label, position) VALUES (?,?,?)",
        [(poll_id, label, i) for i, label in enumerate(options)],
    )
    return poll_id, admin_token


def get_poll_row(conn: sqlite3.Connection, poll_id: str):
    return conn.execute("SELECT * FROM polls WHERE id = ?", (poll_id,)).fetchone()


def poll_is_closed(row) -> bool:
    if row["is_closed"]:
        return True
    if row["closes_at"]:
        return datetime.fromisoformat(row["closes_at"]) <= utcnow()
    return False


def close_poll(conn: sqlite3.Connection, poll_id: str) -> None:
    conn.execute("UPDATE polls SET is_closed = 1 WHERE id = ?", (poll_id,))


def get_results(conn: sqlite3.Connection, poll_id: str) -> dict:
    rows = conn.execute(
        """SELECT o.id, o.label, COUNT(v.id) AS votes
           FROM options o LEFT JOIN votes v ON v.option_id = o.id
           WHERE o.poll_id = ?
           GROUP BY o.id ORDER BY o.position""",
        (poll_id,),
    ).fetchall()
    total = sum(r["votes"] for r in rows)
    return {
        "total_votes": total,
        "options": [
            {
                "id": r["id"],
                "label": r["label"],
                "votes": r["votes"],
                "percent": round(100 * r["votes"] / total, 1) if total else 0.0,
            }
            for r in rows
        ],
    }


def my_vote(conn: sqlite3.Connection, poll_id: str, voter_id: str | None) -> int | None:
    if not voter_id:
        return None
    row = conn.execute(
        "SELECT option_id FROM votes WHERE poll_id = ? AND voter_id = ?", (poll_id, voter_id)
    ).fetchone()
    return row["option_id"] if row else None


def serialize_poll(conn: sqlite3.Connection, row, voter_id: str | None = None) -> dict:
    return {
        "id": row["id"],
        "question": row["question"],
        "created_at": row["created_at"],
        "closes_at": row["closes_at"],
        "is_closed": poll_is_closed(row),
        "my_vote": my_vote(conn, row["id"], voter_id),
        **get_results(conn, row["id"]),
    }


def list_polls(conn: sqlite3.Connection, limit: int = 20) -> list[dict]:
    rows = conn.execute(
        """SELECT p.*, (SELECT COUNT(*) FROM votes v WHERE v.poll_id = p.id) AS total_votes
           FROM polls p ORDER BY p.rowid DESC LIMIT ?""",
        (limit,),
    ).fetchall()
    return [
        {
            "id": r["id"],
            "question": r["question"],
            "created_at": r["created_at"],
            "is_closed": poll_is_closed(r),
            "total_votes": r["total_votes"],
        }
        for r in rows
    ]
