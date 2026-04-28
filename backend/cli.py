"""CLI entry point.

Usage:
    uv run python -m backend.cli create-admin
"""

from __future__ import annotations

import argparse
import getpass
import sys
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session as _Session

from backend.auth import hash_password
from backend.db import Base, SessionLocal, engine
from backend.models import User
from backend.settings import settings


def create_admin(
    username: str,
    password: str,
    session_factory: Callable[[], _Session] = SessionLocal,
) -> None:
    """Insert a single admin user. Aborts if any user already exists."""
    with session_factory() as db:
        existing = db.scalar(select(User).limit(1))
        if existing is not None:
            print(
                f"An admin user already exists: {existing.username}. "
                "This is a single-admin system.",
                file=sys.stderr,
            )
            raise SystemExit(1)
        db.add(User(username=username, password_hash=hash_password(password)))
        db.commit()
    print(f"Created admin user '{username}'.")


def _cmd_create_admin(args: argparse.Namespace) -> None:
    Base.metadata.create_all(engine)

    username = args.username or settings.admin_username or input("Username: ").strip()
    if not username:
        print("Username required.", file=sys.stderr)
        raise SystemExit(2)

    password = args.password or settings.admin_password
    if not password:
        password = getpass.getpass("Password: ")
        confirm = getpass.getpass("Confirm:  ")
        if password != confirm:
            print("Passwords don't match.", file=sys.stderr)
            raise SystemExit(2)

    create_admin(username, password)


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="backend.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    ca = sub.add_parser("create-admin", help="Create the single admin user")
    ca.add_argument("--username", help="(falls back to ADMIN_USERNAME or interactive prompt)")
    ca.add_argument("--password", help="(falls back to ADMIN_PASSWORD or interactive prompt)")
    ca.set_defaults(func=_cmd_create_admin)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
