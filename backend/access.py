"""Personal access links: the way into the private app for real accounts.

On the computer that runs the app:

    python -m backend.access --owner            # your account (the data from before multi-user)
    python -m backend.access --new "Grandpa"    # a new, empty account, e.g. for a relative

It prints a link that works ONCE and only for 15 minutes. Opening it gives that
browser a session for the account (it then stays signed in for a year). Lost the
session (new phone, cleared Safari)? Run the command again for a fresh link.

Like session tokens, only the SHA-256 of the link's secret is stored.
"""

import argparse
import hashlib
import os
import secrets
import socket
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

from backend.db import create_user

LINK_MINUTES = 15


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _ts(moment: datetime) -> str:
    """Fixed-width UTC timestamp, so that comparing the text compares the times
    (plain isoformat() drops the microseconds when they are 0)."""
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds")


def create_access_link(conn: sqlite3.Connection, user_id: str, minutes: int = LINK_MINUTES) -> str:
    """Create a one-time link secret for user_id, valid `minutes`; returns the secret (shown only once)."""
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    with conn:
        conn.execute(
            "INSERT INTO access_links (token_hash, user_id, created_at, expires_at) VALUES (?, ?, ?, ?)",
            (_hash(token), user_id, _ts(now), _ts(now + timedelta(minutes=minutes))),
        )
    return token


def redeem_access_link(conn: sqlite3.Connection, token: str, now: Optional[datetime] = None) -> Optional[str]:
    """Use a link: returns its user_id, or None if unknown, expired or already used."""
    now = now or datetime.now(timezone.utc)
    with conn:
        # One UPDATE that only matches an unused, unexpired link: two browsers opening
        # the same link at the same moment cannot both succeed.
        cursor = conn.execute(
            "UPDATE access_links SET used_at = ? WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?",
            (_ts(now), _hash(token), _ts(now)),
        )
        if cursor.rowcount != 1:
            return None
        row = conn.execute("SELECT user_id FROM access_links WHERE token_hash = ?", (_hash(token),)).fetchone()
    return row[0]


def owner_user(conn: sqlite3.Connection) -> str:
    """The owner account (data from before multi-user), created empty if there is none."""
    row = conn.execute("SELECT id FROM users WHERE label = 'owner' ORDER BY created_at LIMIT 1").fetchone()
    return row[0] if row else create_user(conn, label="owner")


def _local_ip() -> Optional[str]:
    """This computer's address on the local network (for opening the link from a phone)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("192.0.2.1", 80))  # documentation address: nothing is actually sent
            return s.getsockname()[0]
    except OSError:
        return None


def main(argv=None) -> int:
    from backend.transactions import connect  # imported here: transactions imports db, keep startup light

    parser = argparse.ArgumentParser(description="Print a one-time access link to the private app.")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--owner", action="store_true", help="your own account (data from before multi-user)")
    who.add_argument("--new", metavar="NAME", help="create a new empty account with this label")
    args = parser.parse_args(argv)

    conn = connect()
    user_id = owner_user(conn) if args.owner else create_user(conn, label=args.new)
    token = create_access_link(conn, user_id)

    base = os.environ.get("APP_URL")
    bases = [base.rstrip("/")] if base else ["http://127.0.0.1:8000"] + (
        [f"http://{_local_ip()}:8000"] if _local_ip() else [])
    print(f"One-time access link for {'your account' if args.owner else repr(args.new)} "
          f"(valid {LINK_MINUTES} minutes, works once):")
    for b in bases:
        print(f"  {b}/join/{token}")
    if not base:
        print("(Same link, two addresses: this computer, or a phone on the same Wi-Fi. "
              "Set APP_URL to print the public HTTPS address instead.)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
