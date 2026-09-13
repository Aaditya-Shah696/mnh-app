"""Create or reset the two LOCAL DEVELOPMENT accounts with fixed passwords.

    python scripts/dev_users.py

Refuses to run when DISCHARGE_ENV=production: production users are created
with scripts/create_user.py, which prompts for a password and never prints
one. Idempotent: re-running resets the passwords, unlocks and reactivates
the accounts, and never touches any other user.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import inspect, select  # noqa: E402

from app import auth, config, models  # noqa: E402
from app.database import SessionLocal, engine  # noqa: E402

DEV_USERS = (
    # username,   display name,       role,    password
    ("mitesh",    "Dr. Mitesh Shah",  "admin", "dev-admin-password-1"),
    ("reception", "Reception desk",   "staff", "dev-staff-password-1"),
)


def ensure_dev_users(db) -> list[str]:
    """Create or reset DEV_USERS. Returns the usernames touched."""
    if config.IS_PRODUCTION:
        raise RuntimeError("Refusing to create fixed-password dev users: DISCHARGE_ENV=production")
    touched = []
    for username, display_name, role, password in DEV_USERS:
        user = db.scalars(select(models.User).where(models.User.username == username)).first()
        if user is None:
            user = models.User(username=username, display_name=display_name, role=role,
                               password_hash=auth.hash_password(password), is_active=True)
            db.add(user)
        else:
            user.display_name = display_name
            user.role = role
            user.is_active = True
            user.password_hash = auth.hash_password(password)
            user.password_changed_at = models.utcnow()
            auth.unlock_user(user)
        touched.append(username)
    db.commit()
    return touched


def main() -> None:
    config.ensure_dirs()
    if "users" not in inspect(engine).get_table_names():
        sys.exit("The users table does not exist. Run `alembic upgrade head` first.")
    db = SessionLocal()
    try:
        try:
            ensure_dev_users(db)
        except RuntimeError as exc:
            sys.exit(str(exc))
    finally:
        db.close()
    print("Development accounts ready (data dir: %s)" % config.DATA_DIR)
    print(f"  {'username':<12} {'role':<6} password")
    for username, _, role, password in DEV_USERS:
        print(f"  {username:<12} {role:<6} {password}")
    print("Never use these on a machine that leaves the building.")


if __name__ == "__main__":
    main()
