from __future__ import annotations

import argparse
import os
import secrets
from dataclasses import dataclass

from sqlmodel import Session

from app.config import Settings
from app.db import create_db_and_tables, session_scope
from app.schemas import AdminRole
from app.services.admin_auth import (
    create_admin_user,
    get_admin_user_by_username,
    normalize_username,
    update_admin_user,
)


DEFAULT_USERNAME = "ui-agent"
DEFAULT_FULL_NAME = "UI Test Agent"
DEFAULT_ROLE = AdminRole.editor
USERNAME_ENV = "UI_TEST_ADMIN_USERNAME"
FULL_NAME_ENV = "UI_TEST_ADMIN_FULL_NAME"
EMAIL_ENV = "UI_TEST_ADMIN_EMAIL"
AVATAR_URL_ENV = "UI_TEST_ADMIN_AVATAR_URL"
ROLE_ENV = "UI_TEST_ADMIN_ROLE"
PASSWORD_FILE_ENV = "UI_TEST_ADMIN_PASSWORD_FILE"
ALLOWED_TEST_USERNAME_PREFIXES = ("ui-", "qa-", "test-")
settings = Settings()


@dataclass(slots=True)
class EnsureTestAdminResult:
    action: str
    username: str
    password: str
    generated_password: bool
    role: str


def _optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _env_or_default(name: str, default: str | None = None) -> str | None:
    normalized = _optional_text(os.environ.get(name))
    if normalized is None:
        return default
    return normalized


def _read_password_file(path: str | None) -> str | None:
    normalized_path = _optional_text(path)
    if normalized_path is None:
        return None
    with open(normalized_path, encoding="utf-8") as handle:
        return _optional_text(handle.read())


def _validate_test_username(username: str) -> None:
    normalized_username = normalize_username(username)
    if not normalized_username:
        raise ValueError("Test usernames cannot be blank.")
    if normalized_username == normalize_username(settings.admin_bootstrap_username):
        raise ValueError("Refusing to manage the bootstrap admin account with the UI test-user helper.")
    if not normalized_username.startswith(ALLOWED_TEST_USERNAME_PREFIXES):
        allowed_prefixes = ", ".join(ALLOWED_TEST_USERNAME_PREFIXES)
        raise ValueError(f"Test usernames must start with one of: {allowed_prefixes}.")


def ensure_test_admin_user(
    session: Session,
    *,
    username: str,
    password: str | None,
    full_name: str | None = None,
    email: str | None = None,
    avatar_url: str | None = None,
    role: AdminRole | str = DEFAULT_ROLE,
    must_change_password: bool = False,
) -> EnsureTestAdminResult:
    _validate_test_username(username)
    normalized_password = _optional_text(password)
    generated_password = normalized_password is None
    effective_password = normalized_password or secrets.token_urlsafe(18)

    existing_user = get_admin_user_by_username(session, username)
    if existing_user is None:
        user = create_admin_user(
            session,
            username=username,
            full_name=full_name,
            email=email,
            avatar_url=avatar_url,
            password=effective_password,
            is_active=True,
            role=role,
            must_change_password=must_change_password,
        )
        return EnsureTestAdminResult(
            action="created",
            username=user.username,
            password=effective_password,
            generated_password=generated_password,
            role=str(user.role),
        )

    updated_user = update_admin_user(
        session,
        existing_user,
        full_name=full_name,
        email=email,
        avatar_url=avatar_url,
        password=effective_password,
        is_active=True,
        role=role,
        must_change_password=must_change_password,
    )
    return EnsureTestAdminResult(
        action="updated",
        username=updated_user.username,
        password=effective_password,
        generated_password=generated_password,
        role=str(updated_user.role),
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create or reset a dedicated local admin account for browser/UI testing.",
    )
    parser.add_argument("--username", default=_env_or_default(USERNAME_ENV, DEFAULT_USERNAME))
    parser.add_argument("--password-file", default=_env_or_default(PASSWORD_FILE_ENV))
    parser.add_argument("--full-name", default=_env_or_default(FULL_NAME_ENV, DEFAULT_FULL_NAME))
    parser.add_argument("--email", default=_env_or_default(EMAIL_ENV))
    parser.add_argument("--avatar-url", default=_env_or_default(AVATAR_URL_ENV))
    parser.add_argument("--role", default=_env_or_default(ROLE_ENV, DEFAULT_ROLE.value))
    parser.add_argument(
        "--must-change-password",
        action="store_true",
        help="Require a password rotation on first sign-in instead of leaving the account immediately usable.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()

    create_db_and_tables()

    with session_scope() as session:
        result = ensure_test_admin_user(
            session,
            username=args.username,
            password=_read_password_file(args.password_file),
            full_name=_optional_text(args.full_name),
            email=_optional_text(args.email),
            avatar_url=_optional_text(args.avatar_url),
            role=args.role,
            must_change_password=args.must_change_password,
        )

    if result.generated_password:
        print(
            f"{result.action} test admin '{result.username}' with role '{result.role}'. "
            f"generated_password='{result.password}'"
        )
    else:
        print(f"{result.action} test admin '{result.username}' with role '{result.role}'. Password updated from file input.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
