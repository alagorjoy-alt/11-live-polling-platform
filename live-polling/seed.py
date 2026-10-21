"""Create sample polls with votes so the demo has data. Usage: python seed.py"""
import random

from app.database import db, init_db
from app.polls import create_poll

SAMPLES = [
    ("Which feature should we build next?", ["Dark mode", "Export to CSV", "Slack alerts", "Mobile app"]),
    ("Best day for the team meetup?", ["Tuesday", "Wednesday", "Thursday"]),
    ("Favourite backend language?", ["Python", "Java", "Node.js", "Go"]),
]


def main() -> None:
    init_db()
    random.seed(7)
    with db() as conn:
        for question, options in SAMPLES:
            poll_id, _ = create_poll(conn, question, options, None)
            ids = [r["id"] for r in conn.execute("SELECT id FROM options WHERE poll_id=?", (poll_id,))]
            for n in range(random.randint(8, 25)):
                conn.execute(
                    "INSERT INTO votes (poll_id, option_id, voter_id, created_at) VALUES (?,?,?,datetime('now'))",
                    (poll_id, random.choice(ids), f"seed-voter-{poll_id}-{n:04d}-padding"),
                )
            print(f"seeded /p/{poll_id}  {question}")


if __name__ == "__main__":
    main()
