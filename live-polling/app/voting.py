"""Vote rules: the one place that decides whether a vote is allowed."""
import sqlite3

from .polls import get_poll_row, poll_is_closed, utcnow


class PollNotFound(Exception):
    pass


class PollClosed(Exception):
    pass


class InvalidOption(Exception):
    pass


class DuplicateVote(Exception):
    pass


def cast_vote(conn: sqlite3.Connection, poll_id: str, option_id: int,
              voter_id: str, ip_hash: str | None) -> None:
    poll = get_poll_row(conn, poll_id)
    if poll is None:
        raise PollNotFound(poll_id)
    if poll_is_closed(poll):
        raise PollClosed(poll_id)

    option = conn.execute(
        "SELECT id FROM options WHERE id = ? AND poll_id = ?", (option_id, poll_id)
    ).fetchone()
    if option is None:
        raise InvalidOption(option_id)

    try:
        conn.execute(
            "INSERT INTO votes (poll_id, option_id, voter_id, ip_hash, created_at) VALUES (?,?,?,?,?)",
            (poll_id, option_id, voter_id, ip_hash, utcnow().isoformat(timespec="seconds")),
        )
    except sqlite3.IntegrityError as exc:
        # The UNIQUE constraints are the real guard: two simultaneous requests
        # from the same voter can never both succeed.
        raise DuplicateVote(voter_id) from exc
