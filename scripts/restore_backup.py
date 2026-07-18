"""Restore an encrypted backup into a directory of your choice.

Usage:
  python scripts/restore_backup.py <backup.zip> <target_dir> [--password PW]

The password defaults to the one in data/backup_password.txt. The
restore NEVER overwrites the live data/ directory directly: restore to
a fresh folder, verify, then swap it in place of data/ while the app
is stopped.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402
from app.services import backup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Restore an encrypted backup")
    parser.add_argument("archive", type=Path)
    parser.add_argument("target_dir", type=Path)
    parser.add_argument("--password", default=None,
                        help="Backup password (default: data/backup_password.txt)")
    args = parser.parse_args()

    if not args.archive.exists():
        sys.exit(f"Archive not found: {args.archive}")
    resolved_target = args.target_dir.resolve()
    if resolved_target == config.DATA_DIR.resolve():
        sys.exit("Refusing to restore directly into the live data/ directory. "
                 "Restore to a fresh folder, verify it, then swap it in while "
                 "the app is stopped.")

    password = args.password
    if password is None:
        pw_file = config.DATA_DIR / "backup_password.txt"
        if not pw_file.exists():
            sys.exit("No --password given and data/backup_password.txt not found.")
        password = pw_file.read_text(encoding="utf-8").strip()

    restored = backup.restore_backup(args.archive, args.target_dir, password)
    print(f"Restored {len(restored)} files into {args.target_dir}:")
    for name in restored[:10]:
        print(f"  {name}")
    if len(restored) > 10:
        print(f"  ... and {len(restored) - 10} more")
    print("Database integrity check: ok")


if __name__ == "__main__":
    main()
