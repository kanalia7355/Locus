"""Explicit local provisioning. Never put passwords in argv or source files."""

import argparse
import getpass
from pathlib import Path

from app.service import Service


def main() -> None:
    parser = argparse.ArgumentParser(description="Locus synthetic-data development administration")
    parser.add_argument("command", choices=["provision", "project", "assign", "seed-synthetic"])
    parser.add_argument("--username")
    parser.add_argument("--system-admin", action="store_true")
    parser.add_argument("--project", default="development")
    parser.add_argument("--org", default="development")
    parser.add_argument("--name", default="検証用プロジェクト")
    parser.add_argument("--role", default="researcher")
    parser.add_argument("--shared", action="store_true")
    args = parser.parse_args()
    svc = Service(Path(__file__).resolve().parents[2] / "storage" / "locus.sqlite3")
    try:
        if args.command == "project":
            svc.create_project(args.org, args.project, args.name)
        else:
            if not args.username:
                parser.error("--username is required")
            if args.command == "provision":
                first = getpass.getpass("Temporary password (14–128 characters): ")
                if first != getpass.getpass("Confirm temporary password: "):
                    parser.error("Passwords do not match")
                svc.provision(args.username, first, system_admin=args.system_admin)
            elif args.command == "assign":
                svc.assign(args.username, args.project, args.role)
            else:
                svc.seed_synthetic(
                    args.username, args.project, "shared" if args.shared else "personal"
                )
        print("Local operation complete. Use synthetic data only.")
    finally:
        svc.close()


if __name__ == "__main__":
    main()
