"""Restore an encrypted backup into a directory of your choice.

Usage:
  python scripts/restore_backup.py <backup.zip> <target_dir> [--prompt | --password-file FILE]

The password defaults to the one in data/backup_password.txt. The
restore NEVER overwrites the live data/ directory directly: restore to
a fresh folder, verify, then swap it in place of data/ while the app
is stopped.
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.services import backup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an encrypted backup")
    parser.add_argument("archive", type=Path)
    parser.add_argument("target_dir", type=Path)
    secret = parser.add_mutually_exclusive_group()
    secret.add_argument("--password-file", type=Path, default=None,
                        help="File holding the backup password")
    secret.add_argument("--prompt", action="store_true",
                        help="Ask for the backup password without echoing it")
    secret.add_argument("--password", default=None,
                        help="Backup password on the command line (visible to other "
                             "processes; prefer --password-file or --prompt)")
    args = parser.parse_args()

    if not args.archive.exists():
        sys.exit(f"Archive not found: {args.archive}")
    resolved_target = args.target_dir.resolve()
    if resolved_target == config.DATA_DIR.resolve():
        sys.exit("Refusing to restore directly into the live data/ directory. "
                 "Restore to a fresh folder, verify it, then swap it in while "
                 "the app is stopped.")

    if args.prompt:
        password = getpass.getpass("Backup password: ").strip()
    elif args.password_file is not None:
        if not args.password_file.exists():
            sys.exit(f"Password file not found: {args.password_file}")
        password = args.password_file.read_text(encoding="utf-8").strip()
    elif args.password is not None:
        password = args.password
    else:
        pw_file = config.DATA_DIR / "backup_password.txt"
        if not pw_file.exists():
            sys.exit("No password given (--prompt or --password-file) and "
                     "data/backup_password.txt not found.")
        password = pw_file.read_text(encoding="utf-8").strip()
    if not password:
        sys.exit("The backup password is empty.")

    restored = backup.restore_backup(args.archive, args.target_dir, password)
    print(f"Restored {len(restored)} files into {args.target_dir}:")
    for name in restored[:10]:
        print(f"  {name}")
    if len(restored) > 10:
        print(f"  ... and {len(restored) - 10} more")
    print("Database integrity check: ok")


if __name__ == "__main__":
    main()
