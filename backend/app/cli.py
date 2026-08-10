import argparse
import getpass
import sys
from collections.abc import Sequence
from pathlib import Path

from app.config import get_settings
from app.db import SessionFactory
from app.services.auth import PasswordStore
from app.services.backup import export_backup, write_backup_json


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="what2build")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser(
        "reset-password",
        help="replace the shared password and invalidate existing sessions",
    )
    export_parser = commands.add_parser("export-backup", help="write a versioned personal-data backup")
    export_parser.add_argument("path", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "export-backup":
        target: Path = args.path
        with SessionFactory() as session:
            backup = export_backup(session)
        try:
            write_backup_json(target, backup)
        except FileExistsError:
            print(f"Refusing to overwrite existing file: {target}", file=sys.stderr)
            return 1
        print(f"{target} owned_sets={len(backup.owned_sets)} missing_parts={len(backup.missing_parts)}")
        return 0
    if args.command != "reset-password":
        return 1

    password = getpass.getpass("New password: ")
    confirmation = getpass.getpass("Confirm new password: ")
    if password != confirmation:
        print("Passwords do not match.", file=sys.stderr)
        return 1

    settings = get_settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    with SessionFactory() as session:
        PasswordStore(session).set_password(password)
    print("Password reset; existing sessions have been invalidated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
