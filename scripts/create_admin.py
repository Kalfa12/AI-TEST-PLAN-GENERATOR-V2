"""Create or report the first admin user for a deployment.

Usage:
    python scripts/create_admin.py --email admin@example.com --password 'change-me'
"""

from __future__ import annotations

import argparse
import asyncio

from ai_testplan_generator.api.security.password import hash_password
from ai_testplan_generator.config import Settings
from ai_testplan_generator.domain.users import UserRepository


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Create an admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default="Admin")
    parser.add_argument("--db", default=None, help="Defaults to APP_DB_PATH from settings.")
    return parser


async def _main() -> int:
    args = _parser().parse_args()
    db_path = args.db or Settings().app_db_path
    repo = await UserRepository.create(db_path=db_path)
    try:
        existing = await repo.get_by_email(args.email)
        if existing is not None:
            print(
                f"User already exists: {existing.email} "
                f"(id={existing.id}, admin={existing.is_admin})"
            )
            return 0 if existing.is_admin else 2
        user = await repo.create_user(
            email=args.email,
            display_name=args.name,
            password_hash=hash_password(args.password),
            is_admin=True,
        )
        print(f"Created admin user: {user.email} (id={user.id})")
        return 0
    finally:
        await repo.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
