"""Create, list, or reset users from the command line.

There is deliberately no web-based first-run wizard: the first admin is
created here, over SSH, by someone who already has the server.

Usage:
  python scripts/create_user.py --admin --username mitesh --display-name "Dr. Mitesh Shah"
  python scripts/create_user.py --username reception --display-name "Reception desk"
  python scripts/create_user.py --list
  python scripts/create_user.py --reset-password --username reception

The password is always prompted for (twice) and never taken as an argument
so it does not land in shell history.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from fastapi import HTTPException  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app import auth, config, models  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402


def _prompt_password(username: str) -> str:
    while True:
        first = getpass.getpass("Password: ")
        second = getpass.getpass("Repeat password: ")
        if first != second:
            print("Passwords do not match, try again.")
            continue
        try:
            auth.validate_new_password(first, username)
        except HTTPException as exc:
            print(exc.detail)
            continue
        return first


def _ensure_schema() -> None:
    from sqlalchemy import inspect

    if "users" not in inspect(engine).get_table_names():
        sys.exit("The users table does not exist. Run `alembic upgrade head` first.")


def cmd_list(db) -> None:
    users = db.scalars(select(models.User).order_by(models.User.username)).all()
    if not users:
        print("No users yet.")
        return
    print(f"{'username':<20} {'role':<6} {'active':<7} {'last login':<20} display name")
    for u in users:
        last = u.last_login_at.isoformat(timespec="minutes") if u.last_login_at else "-"
        print(f"{u.username:<20} {u.role:<6} {str(u.is_active):<7} {last:<20} {u.display_name}")


def cmd_create(db, username: str, display_name: str, role: str) -> None:
    username = username.strip().lower()
    if db.scalars(select(models.User).where(models.User.username == username)).first():
        sys.exit(f"User {username!r} already exists.")
    password = _prompt_password(username)
    user = models.User(
        username=username, display_name=display_name.strip(), role=role,
        password_hash=auth.hash_password(password), is_active=True,
    )
    db.add(user)
    db.flush()
    db.add(models.AuditLog(
        user_id=None, username="cli", action="user.create", entity_type="user",
        entity_id=user.id, detail=f'{{"username":"{username}","role":"{role}","via":"cli"}}',
    ))
    db.commit()
    print(f"Created {role} user {username!r} ({display_name}).")


def cmd_reset(db, username: str) -> None:
    username = username.strip().lower()
    user = db.scalars(select(models.User).where(models.User.username == username)).first()
    if user is None:
        sys.exit(f"No user {username!r}.")
    password = _prompt_password(username)
    user.password_hash = auth.hash_password(password)
    user.password_changed_at = models.utcnow()
    auth.unlock_user(user)
    user.is_active = True
    revoked = auth.revoke_user_sessions(db, user.id)
    db.add(models.AuditLog(
        user_id=None, username="cli", action="user.reset_password", entity_type="user",
        entity_id=user.id,
        detail=f'{{"username":"{username}","sessions_revoked":{revoked},"via":"cli"}}',
    ))
    db.commit()
    print(f"Password reset for {username!r}; {revoked} session(s) revoked; account unlocked and active.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage MNH Discharge Records users")
    parser.add_argument("--list", action="store_true", help="List users")
    parser.add_argument("--reset-password", action="store_true",
                        help="Reset the password of --username (also unlocks and reactivates)")
    parser.add_argument("--admin", action="store_true", help="Create an admin (default: staff)")
    parser.add_argument("--username")
    parser.add_argument("--display-name")
    args = parser.parse_args()

    config.ensure_dirs()
    _ensure_schema()
    db = SessionLocal()
    try:
        if args.list:
            cmd_list(db)
        elif args.reset_password:
            if not args.username:
                parser.error("--reset-password needs --username")
            cmd_reset(db, args.username)
        else:
            if not args.username or not args.display_name:
                parser.error("--username and --display-name are required to create a user")
            cmd_create(db, args.username, args.display_name, "admin" if args.admin else "staff")
    finally:
        db.close()


if __name__ == "__main__":
    main()
