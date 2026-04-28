import pytest
from sqlalchemy import select

from backend.auth import verify_password
from backend.cli import create_admin
from backend.models import User


def test_create_admin_inserts_a_hashed_user(db_factory):
    Session = db_factory
    with Session() as s:
        for u in s.scalars(select(User)).all():
            s.delete(u)
        s.commit()

    create_admin("ada", "lovelace", session_factory=Session)

    with Session() as s:
        u = s.scalar(select(User).where(User.username == "ada"))
        assert u is not None
        assert u.password_hash != "lovelace"
        assert verify_password(u.password_hash, "lovelace")


def test_create_admin_refuses_second_user(db_factory):
    Session = db_factory  # already seeds an `admin` user
    with pytest.raises(SystemExit):
        create_admin("second", "x", session_factory=Session)
