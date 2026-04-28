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


def _cmd_build_resume_pdf(args: argparse.Namespace) -> None:
    from backend.pdf import build_pdf_and_update_db, DEFAULT_OUT

    Base.metadata.create_all(engine)
    out = DEFAULT_OUT if args.out is None else __import__("pathlib").Path(args.out)
    with SessionLocal() as db:
        path = build_pdf_and_update_db(db, out)
    print(f"Wrote PDF: {path}")
    print("resume_meta.pdf_path updated to point at the new file.")


def _cmd_dump_content(args: argparse.Namespace) -> None:
    import json
    from pathlib import Path
    from backend.fixtures import dump_content

    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        data = dump_content(db)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {out} with "
          f"{len(data['projects'])} projects, "
          f"{len(data['links'])} links, "
          f"{len(data['posts'])} posts.")


def _cmd_load_content(args: argparse.Namespace) -> None:
    from pathlib import Path
    from backend.fixtures import load_content

    Base.metadata.create_all(engine)
    fixture_path = Path(args.path)
    if not fixture_path.is_file():
        print(f"Fixture file not found: {fixture_path}", file=sys.stderr)
        raise SystemExit(2)

    with SessionLocal() as db:
        result = load_content(db, fixture_path, only_if_empty=args.only_if_empty)
    print(f"Load result: {result}")


def main(argv: list[str] | None = None) -> None:
    p = argparse.ArgumentParser(prog="backend.cli")
    sub = p.add_subparsers(dest="cmd", required=True)

    ca = sub.add_parser("create-admin", help="Create the single admin user")
    ca.add_argument("--username", help="(falls back to ADMIN_USERNAME or interactive prompt)")
    ca.add_argument("--password", help="(falls back to ADMIN_PASSWORD or interactive prompt)")
    ca.set_defaults(func=_cmd_create_admin)

    bp = sub.add_parser(
        "build-resume-pdf",
        help="Render resume_meta.summary (Markdown) into a styled PDF and "
        "point resume_meta.pdf_path at it.",
    )
    bp.add_argument("--out", help="Output path (defaults to frontend/static/resume-generated.pdf)")
    bp.set_defaults(func=_cmd_build_resume_pdf)

    dc = sub.add_parser(
        "dump-content",
        help="Export site_meta, resume_meta, projects, links, and posts to JSON.",
    )
    dc.add_argument("--out", "-o", default="data/content.json",
                    help="Output JSON path (default: data/content.json)")
    dc.set_defaults(func=_cmd_dump_content)

    lc = sub.add_parser(
        "load-content",
        help="Import a content dump produced by dump-content.",
    )
    lc.add_argument("path", help="Path to the JSON fixture")
    lc.add_argument("--only-if-empty", action="store_true",
                    help="Skip the load if the DB already has projects.")
    lc.set_defaults(func=_cmd_load_content)

    args = p.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
