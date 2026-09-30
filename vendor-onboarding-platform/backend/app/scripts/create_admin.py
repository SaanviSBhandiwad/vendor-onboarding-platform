"""Create the first admin account.

    docker compose exec api python -m app.scripts.create_admin --email admin@example.com

The password is prompted for (not echoed) unless --password is given.
"""

import argparse
import getpass
import sys

from pydantic import ValidationError

from app.core.database import SessionLocal
from app.core.exceptions import DuplicateUserError
from app.models import UserRole
from app.schemas.user import UserCreate
from app.services import user_service


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create an admin user")
    parser.add_argument("--email", required=True)
    parser.add_argument("--full-name", default="Administrator")
    parser.add_argument("--password", help="omit to be prompted securely")
    args = parser.parse_args(argv)

    password = args.password or getpass.getpass("Password (min 8 chars, letters and digits): ")
    try:
        data = UserCreate(email=args.email, full_name=args.full_name, password=password, role=UserRole.ADMIN)
    except ValidationError as exc:
        for err in exc.errors():
            print(f"Invalid {'.'.join(map(str, err['loc']))}: {err['msg']}", file=sys.stderr)
        return 1

    with SessionLocal() as db:
        try:
            user = user_service.create_user(db, data, actor="system:create_admin")
        except DuplicateUserError:
            print(f"A user with email {data.email} already exists.", file=sys.stderr)
            return 1
    print(f"Admin created: {user.email} (id {user.id})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
