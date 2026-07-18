"""Run one encrypted backup immediately.

Usage:  python scripts/backup_now.py [--copy-to D:\\some\\folder]

--copy-to also copies the new archive to another drive (external disk,
synced cloud folder) so a copy leaves this machine.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services import backup  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Create an encrypted backup now")
    parser.add_argument("--copy-to", type=Path, default=None,
                        help="Also copy the archive to this folder (external drive)")
    args = parser.parse_args()

    path = backup.create_backup()
    print(f"Backup written: {path} ({path.stat().st_size / 1e6:.1f} MB)")
    print(f"Password file: {backup._password_file()} - keep a copy of this "
          "password somewhere outside this computer.")

    if args.copy_to:
        args.copy_to.mkdir(parents=True, exist_ok=True)
        dest = args.copy_to / path.name
        shutil.copy2(path, dest)
        print(f"Copied to: {dest}")


if __name__ == "__main__":
    main()
