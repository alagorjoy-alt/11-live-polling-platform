"""Fire fake votes at a running server so you can watch the chart move live.

Usage: python demo_votes.py POLL_ID [--url http://localhost:8000] [--count 15] [--delay 0.8]
Each fake voter gets its own cookie jar, so every vote counts as a different browser.
"""
import argparse
import random
import time

import httpx


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("poll_id")
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--count", type=int, default=15)
    ap.add_argument("--delay", type=float, default=0.8)
    args = ap.parse_args()

    poll = httpx.get(f"{args.url}/api/polls/{args.poll_id}").raise_for_status().json()
    option_ids = [o["id"] for o in poll["options"]]
    print(f"Voting on: {poll['question']}")

    for i in range(args.count):
        with httpx.Client() as voter:  # fresh cookie jar = new voter
            res = voter.post(f"{args.url}/api/polls/{args.poll_id}/vote",
                             json={"option_id": random.choice(option_ids)})
            print(f"vote {i + 1}: HTTP {res.status_code}")
        time.sleep(args.delay)


if __name__ == "__main__":
    main()
