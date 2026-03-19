from __future__ import annotations

import base64
import hashlib
import logging
import math
import re
import secrets
import time
from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import timedelta
from threading import Lock
from urllib.parse import urlparse

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import func, or_, select
from sqlmodel import Session

from app.config import Settings
from app.db import get_session
from app.models import AdminSession, AdminUser
from app.rbac import AdminPermission, AdminRole, normalize_admin_role, permissions_for_role, user_has_permission
from app.schemas import AdminUserRead
from app.time_utils import utc_now


LOGGER = logging.getLogger(__name__)
TOKEN_BYTES = 48
SALT_BYTES = 16
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
PROFILE_UNSET = object()
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
bearer_security = HTTPBearer(auto_error=False)
settings = Settings()


@dataclass(slots=True)
class BootstrapAdminResult:
    username: str
    password: str
    generated_password: bool
    weak_password: bool


@dataclass(slots=True)
class AdminContext:
    user: AdminUser
    session: AdminSession


@dataclass(slots=True)
class AdminLoginThrottleError(Exception):
    retry_after_seconds: int


class LoginAttemptLimiter:
    def __init__(self) -> None:
        self._lock = Lock()
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    def clear(self) -> None:
        with self._lock:
            self._attempts.clear()

    def record_failure(self, key: str | None) -> None:
        normalized_key = (key or "").strip()
        if not normalized_key:
            return

        now = time.monotonic()
        with self._lock:
            attempts = self._attempts[normalized_key]
            self._prune(attempts, now)
            attempts.append(now)

    def retry_after_seconds(self, key: str | None, *, max_attempts: int) -> int | None:
        normalized_key = (key or "").strip()
        if not normalized_key or max_attempts <= 0:
            return None

        now = time.monotonic()
        with self._lock:
            attempts = self._attempts.get(normalized_key)
            if not attempts:
                return None

            self._prune(attempts, now)
            if len(attempts) < max_attempts:
                if not attempts:
                    self._attempts.pop(normalized_key, None)
                return None

            retry_after = settings.admin_login_window_seconds - (now - attempts[0])
            return max(1, math.ceil(retry_after))

    def _prune(self, attempts: deque[float], now: float) -> None:
        cutoff = now - settings.admin_login_window_seconds
        while attempts and attempts[0] <= cutoff:
            attempts.popleft()


login_attempt_limiter = LoginAttemptLimiter()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def normalize_optional_profile_text(value: str | None, *, label: str, max_length: int) -> str | None:
    if value is None:
        return None

    normalized = value.strip()
    if not normalized:
        return None

    if len(normalized) > max_length:
        raise ValueError(f"{label} must be {max_length} characters or fewer.")

    return normalized


def normalize_optional_email(email: str | None) -> str | None:
    normalized = normalize_optional_profile_text(email, label="Email", max_length=320)
    if normalized is None:
        return None

    lowered = normalized.lower()
    if not EMAIL_PATTERN.match(lowered):
        raise ValueError("Enter a valid email address.")

    return lowered


def normalize_optional_avatar_url(avatar_url: str | None) -> str | None:
    normalized = normalize_optional_profile_text(avatar_url, label="Avatar URL", max_length=1024)
    if normalized is None:
        return None

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Enter a valid profile image URL.")

    return normalized


def build_gravatar_url(seed: str | None) -> str:
    normalized_seed = (seed or "artificer").strip().lower() or "artificer"
    digest = hashlib.md5(normalized_seed.encode("utf-8")).hexdigest()
    return f"https://www.gravatar.com/avatar/{digest}?d=identicon&s=160"


def validate_password_strength(password: str, *, enforce_minimum_length: bool = True) -> None:
    if enforce_minimum_length and len(password) < settings.admin_password_min_length:
        raise ValueError(
            f"Passwords must be at least {settings.admin_password_min_length} characters long."
        )
    if not password.strip():
        raise ValueError("Passwords cannot be blank or whitespace only.")


def _urlsafe_b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def _urlsafe_b64decode(encoded: str) -> bytes:
    padding = "=" * (-len(encoded) % 4)
    return base64.urlsafe_b64decode(f"{encoded}{padding}".encode("ascii"))


def hash_password(password: str, *, enforce_strength: bool = True) -> str:
    validate_password_strength(password, enforce_minimum_length=enforce_strength)
    salt = secrets.token_bytes(SALT_BYTES)
    password_hash = hashlib.scrypt(
        password.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
    )
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{_urlsafe_b64encode(salt)}${_urlsafe_b64encode(password_hash)}"
    )


def verify_password(password: str, encoded_password: str) -> bool:
    try:
        algorithm, raw_n, raw_r, raw_p, salt_value, hash_value = encoded_password.split("$")
        if algorithm != "scrypt":
            return False
        candidate_hash = hashlib.scrypt(
            password.encode("utf-8"),
            salt=_urlsafe_b64decode(salt_value),
            n=int(raw_n),
            r=int(raw_r),
            p=int(raw_p),
        )
        return secrets.compare_digest(candidate_hash, _urlsafe_b64decode(hash_value))
    except (ValueError, TypeError):
        return False


def hash_session_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def get_admin_user_by_username(session: Session, username: str) -> AdminUser | None:
    normalized_username = normalize_username(username)
    if not normalized_username:
        return None
    statement = select(AdminUser).where(AdminUser.username == normalized_username)
    return session.execute(statement).scalars().first()


def get_admin_user(session: Session, user_id: int) -> AdminUser | None:
    return session.get(AdminUser, user_id)


def get_admin_user_by_email(session: Session, email: str) -> AdminUser | None:
    normalized_email = normalize_optional_email(email)
    if normalized_email is None:
        return None
    statement = select(AdminUser).where(AdminUser.email == normalized_email)
    return session.execute(statement).scalars().first()


def reset_login_rate_limits() -> None:
    login_attempt_limiter.clear()


def _seconds_until(timestamp) -> int:
    return max(1, math.ceil((timestamp - utc_now()).total_seconds()))


def _reset_failed_login_state(user: AdminUser) -> None:
    user.failed_login_attempts = 0
    user.last_failed_login_at = None
    user.locked_until = None


def _persist_failed_login_state(session: Session, user: AdminUser) -> None:
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)


def _record_failed_login(session: Session, user: AdminUser | None, *, normalized_username: str, client_ip: str | None) -> None:
    login_attempt_limiter.record_failure(client_ip)

    if user and user.is_active:
        now = utc_now()
        if (
            user.last_failed_login_at is None
            or (now - user.last_failed_login_at) > timedelta(seconds=settings.admin_login_window_seconds)
        ):
            user.failed_login_attempts = 0

        user.failed_login_attempts += 1
        user.last_failed_login_at = now
        if user.failed_login_attempts >= settings.admin_login_max_attempts:
            user.locked_until = now + timedelta(seconds=settings.admin_login_lockout_seconds)
            user.failed_login_attempts = 0
            user.last_failed_login_at = None
            LOGGER.warning(
                "Admin login locked user '%s' after repeated failures from %s.",
                normalized_username or "<blank>",
                client_ip or "unknown",
            )

        _persist_failed_login_state(session, user)

    LOGGER.warning(
        "Admin login failed for username '%s' from %s.",
        normalized_username or "<blank>",
        client_ip or "unknown",
    )


def _ensure_login_allowed(user: AdminUser | None, *, normalized_username: str, client_ip: str | None) -> None:
    retry_after = login_attempt_limiter.retry_after_seconds(
        client_ip,
        max_attempts=settings.admin_login_ip_max_attempts,
    )
    if retry_after is not None:
        LOGGER.warning(
            "Admin login throttled for IP %s while attempting username '%s'.",
            client_ip or "unknown",
            normalized_username or "<blank>",
        )
        raise AdminLoginThrottleError(retry_after_seconds=retry_after)

    if user and user.locked_until and user.locked_until > utc_now():
        retry_after = _seconds_until(user.locked_until)
        LOGGER.warning(
            "Admin login blocked for locked user '%s' from %s.",
            normalized_username or "<blank>",
            client_ip or "unknown",
        )
        raise AdminLoginThrottleError(retry_after_seconds=retry_after)


def list_admin_users(session: Session) -> list[AdminUser]:
    statement = select(AdminUser).order_by(AdminUser.username.asc())
    return list(session.execute(statement).scalars())


def _count_admin_users(session: Session) -> int:
    statement = select(func.count()).select_from(AdminUser)
    return int(session.execute(statement).scalar_one())


def count_active_superusers(session: Session, *, exclude_user_id: int | None = None) -> int:
    statement = select(func.count()).select_from(AdminUser).where(
        AdminUser.is_active == True,
        or_(
            AdminUser.role == AdminRole.superuser.value,
            AdminUser.is_superuser == True,
        ),
    )
    if exclude_user_id is not None:
        statement = statement.where(AdminUser.id != exclude_user_id)
    return int(session.execute(statement).scalar_one())


def resolve_admin_role(user: AdminUser) -> AdminRole:
    return normalize_admin_role(user.role, fallback_is_superuser=user.is_superuser)


def build_admin_user_read(user: AdminUser) -> AdminUserRead:
    role = resolve_admin_role(user)
    return AdminUserRead(
        id=int(user.id or 0),
        username=user.username,
        full_name=user.full_name,
        email=user.email,
        avatar_url=user.avatar_url,
        gravatar_url=build_gravatar_url(user.email or user.username),
        is_active=user.is_active,
        role=role,
        permissions=permissions_for_role(role),
        is_superuser=role == AdminRole.superuser,
        must_change_password=user.must_change_password,
        last_login_at=user.last_login_at,
        password_changed_at=user.password_changed_at,
        created_at=user.created_at,
        updated_at=user.updated_at,
    )


def ensure_bootstrap_admin(session: Session) -> BootstrapAdminResult | None:
    if _count_admin_users(session) > 0:
        return None

    username = normalize_username(settings.admin_bootstrap_username)
    if not username:
        raise RuntimeError("ADMIN_BOOTSTRAP_USERNAME must not be blank.")

    password = settings.admin_bootstrap_password or secrets.token_urlsafe(18)
    generated_password = settings.admin_bootstrap_password is None
    weak_password = len(password) < settings.admin_password_min_length
    enforce_strength = generated_password or not weak_password
    password_hash = hash_password(password, enforce_strength=enforce_strength)
    timestamp = utc_now()

    bootstrap_user = AdminUser(
        username=username,
        password_hash=password_hash,
        is_active=True,
        role=AdminRole.superuser,
        is_superuser=True,
        must_change_password=True,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(bootstrap_user)
    session.commit()

    return BootstrapAdminResult(
        username=username,
        password=password,
        generated_password=generated_password,
        weak_password=weak_password,
    )


def create_admin_user(
    session: Session,
    *,
    username: str,
    full_name: str | None = None,
    email: str | None = None,
    avatar_url: str | None = None,
    password: str,
    is_active: bool,
    role: AdminRole | str,
    must_change_password: bool,
) -> AdminUser:
    normalized_username = normalize_username(username)
    if not normalized_username:
        raise ValueError("Usernames cannot be blank.")
    if get_admin_user_by_username(session, normalized_username):
        raise ValueError("That username is already in use.")
    normalized_full_name = normalize_optional_profile_text(full_name, label="Full name", max_length=160)
    normalized_email = normalize_optional_email(email)
    normalized_avatar_url = normalize_optional_avatar_url(avatar_url)
    if normalized_email is not None:
        existing_user = get_admin_user_by_email(session, normalized_email)
        if existing_user:
            raise ValueError("That email address is already in use.")

    normalized_role = normalize_admin_role(role)
    timestamp = utc_now()
    user = AdminUser(
        username=normalized_username,
        full_name=normalized_full_name,
        email=normalized_email,
        avatar_url=normalized_avatar_url,
        password_hash=hash_password(password),
        is_active=is_active,
        role=normalized_role,
        is_superuser=normalized_role == AdminRole.superuser,
        must_change_password=must_change_password,
        password_changed_at=None if must_change_password else timestamp,
        created_at=timestamp,
        updated_at=timestamp,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def update_admin_user(
    session: Session,
    user: AdminUser,
    *,
    username: str | None = None,
    full_name: str | None | object = PROFILE_UNSET,
    email: str | None | object = PROFILE_UNSET,
    avatar_url: str | None | object = PROFILE_UNSET,
    password: str | None = None,
    is_active: bool | None = None,
    role: AdminRole | str | None = None,
    must_change_password: bool | None = None,
) -> AdminUser:
    timestamp = utc_now()

    if username is not None:
        normalized_username = normalize_username(username)
        if not normalized_username:
            raise ValueError("Usernames cannot be blank.")
        existing_user = get_admin_user_by_username(session, normalized_username)
        if existing_user and existing_user.id != user.id:
            raise ValueError("That username is already in use.")
        user.username = normalized_username

    if full_name is not PROFILE_UNSET:
        user.full_name = normalize_optional_profile_text(full_name, label="Full name", max_length=160)

    if email is not PROFILE_UNSET:
        normalized_email = normalize_optional_email(email)
        if normalized_email is not None:
            existing_user = get_admin_user_by_email(session, normalized_email)
            if existing_user and existing_user.id != user.id:
                raise ValueError("That email address is already in use.")
        user.email = normalized_email

    if avatar_url is not PROFILE_UNSET:
        user.avatar_url = normalize_optional_avatar_url(avatar_url)

    if password is not None:
        user.password_hash = hash_password(password)
        user.password_changed_at = timestamp
        if must_change_password is None:
            user.must_change_password = True

    if is_active is not None:
        user.is_active = is_active

    if role is not None:
        normalized_role = normalize_admin_role(role)
        user.role = normalized_role
        user.is_superuser = normalized_role == AdminRole.superuser

    if must_change_password is not None:
        user.must_change_password = must_change_password
        if not must_change_password and user.password_changed_at is None:
            user.password_changed_at = timestamp

    user.updated_at = timestamp
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def delete_admin_user(session: Session, user: AdminUser) -> None:
    statement = select(AdminSession).where(AdminSession.user_id == user.id)
    admin_sessions = list(session.execute(statement).scalars())
    for admin_session in admin_sessions:
        session.delete(admin_session)

    session.delete(user)
    session.commit()


def authenticate_admin_user(
    session: Session,
    username: str,
    password: str,
    *,
    client_ip: str | None = None,
) -> AdminUser | None:
    normalized_username = normalize_username(username)
    user = get_admin_user_by_username(session, normalized_username)
    _ensure_login_allowed(user, normalized_username=normalized_username, client_ip=client_ip)

    if not user or not user.is_active:
        _record_failed_login(session, None, normalized_username=normalized_username, client_ip=client_ip)
        return None
    if not verify_password(password, user.password_hash):
        _record_failed_login(session, user, normalized_username=normalized_username, client_ip=client_ip)
        return None

    if user.failed_login_attempts or user.last_failed_login_at or user.locked_until:
        _reset_failed_login_state(user)
        user.updated_at = utc_now()
        session.add(user)

    LOGGER.info(
        "Admin login succeeded for username '%s' from %s.",
        normalized_username or "<blank>",
        client_ip or "unknown",
    )
    return user


def create_admin_session(session: Session, user: AdminUser, *, remember_me: bool) -> tuple[str, AdminSession]:
    raw_token = secrets.token_urlsafe(TOKEN_BYTES)
    issued_at = utc_now()
    ttl = timedelta(days=settings.admin_remember_me_ttl_days) if remember_me else timedelta(hours=settings.admin_session_ttl_hours)
    admin_session = AdminSession(
        user_id=user.id,
        token_hash=hash_session_token(raw_token),
        remember_me=remember_me,
        expires_at=issued_at + ttl,
        created_at=issued_at,
        last_used_at=issued_at,
    )
    user.last_login_at = issued_at
    user.updated_at = issued_at
    session.add(user)
    session.add(admin_session)
    session.commit()
    session.refresh(user)
    session.refresh(admin_session)
    return raw_token, admin_session


def revoke_admin_session(session: Session, admin_session: AdminSession) -> None:
    admin_session.revoked_at = utc_now()
    admin_session.last_used_at = admin_session.revoked_at
    session.add(admin_session)
    session.commit()


def revoke_user_sessions(session: Session, user_id: int, *, exclude_session_id: int | None = None) -> None:
    timestamp = utc_now()
    statement = select(AdminSession).where(
        AdminSession.user_id == user_id,
        AdminSession.revoked_at.is_(None),
    )
    sessions = list(session.execute(statement).scalars())
    changed = False
    for admin_session in sessions:
        if exclude_session_id is not None and admin_session.id == exclude_session_id:
            continue
        admin_session.revoked_at = timestamp
        admin_session.last_used_at = timestamp
        session.add(admin_session)
        changed = True

    if changed:
        session.commit()


def update_own_account(
    session: Session,
    user: AdminUser,
    *,
    username: str | None = None,
    full_name: str | None | object = PROFILE_UNSET,
    email: str | None | object = PROFILE_UNSET,
    avatar_url: str | None | object = PROFILE_UNSET,
) -> AdminUser:
    if username is None and full_name is PROFILE_UNSET and email is PROFILE_UNSET and avatar_url is PROFILE_UNSET:
        session.refresh(user)
        return user

    if username is not None:
        normalized_username = normalize_username(username)
        if not normalized_username:
            raise ValueError("Usernames cannot be blank.")

        existing_user = get_admin_user_by_username(session, normalized_username)
        if existing_user and existing_user.id != user.id:
            raise ValueError("That username is already in use.")

        if user.username != normalized_username:
            user.username = normalized_username

    if full_name is not PROFILE_UNSET:
        user.full_name = normalize_optional_profile_text(full_name, label="Full name", max_length=160)

    if email is not PROFILE_UNSET:
        normalized_email = normalize_optional_email(email)
        if normalized_email is not None:
            existing_user = get_admin_user_by_email(session, normalized_email)
            if existing_user and existing_user.id != user.id:
                raise ValueError("That email address is already in use.")
        user.email = normalized_email

    if avatar_url is not PROFILE_UNSET:
        user.avatar_url = normalize_optional_avatar_url(avatar_url)

    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    session.refresh(user)

    return user


def update_own_password(
    session: Session,
    user: AdminUser,
    *,
    current_password: str,
    new_password: str,
) -> AdminUser:
    if not verify_password(current_password, user.password_hash):
        raise ValueError("Your current password was incorrect.")
    if current_password == new_password:
        raise ValueError("Choose a new password instead of reusing the current one.")

    timestamp = utc_now()
    user.password_hash = hash_password(new_password)
    user.password_changed_at = timestamp
    user.must_change_password = False
    user.updated_at = timestamp
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def _load_context_from_token(session: Session, token: str) -> AdminContext | None:
    statement = select(AdminSession).where(AdminSession.token_hash == hash_session_token(token))
    admin_session = session.execute(statement).scalars().first()
    if not admin_session:
        return None
    if admin_session.revoked_at is not None or admin_session.expires_at <= utc_now():
        if admin_session.revoked_at is None:
            admin_session.revoked_at = utc_now()
            admin_session.last_used_at = admin_session.revoked_at
            session.add(admin_session)
            session.commit()
        return None

    user = get_admin_user(session, admin_session.user_id)
    if not user or not user.is_active:
        return None

    return AdminContext(user=user, session=admin_session)


def get_admin_context(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_security),
    session: Session = Depends(get_session),
) -> AdminContext:
    if not credentials or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Admin authentication is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    context = _load_context_from_token(session, credentials.credentials)
    if context is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Your admin session is invalid or has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return context


def require_admin_access(context: AdminContext = Depends(get_admin_context)) -> AdminContext:
    if context.user.must_change_password:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Password change required before accessing the admin API.",
        )
    return context


def require_superuser_access(context: AdminContext = Depends(require_admin_access)) -> AdminContext:
    if resolve_admin_role(context.user) != AdminRole.superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only superusers can manage admin accounts.",
        )
    return context


PERMISSION_ERROR_MESSAGES: dict[AdminPermission, str] = {
    AdminPermission.routes_read: "Your role cannot browse route definitions.",
    AdminPermission.routes_write: "Your role cannot create, edit, import, or delete routes.",
    AdminPermission.routes_preview: "Your role cannot run admin preview tools.",
    AdminPermission.users_manage: "Only superusers can manage admin accounts.",
}


def require_admin_permission(permission: AdminPermission):
    def dependency(context: AdminContext = Depends(require_admin_access)) -> AdminContext:
        if not user_has_permission(context.user, permission):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=PERMISSION_ERROR_MESSAGES[permission],
            )
        return context

    return dependency


require_route_read_access = require_admin_permission(AdminPermission.routes_read)
require_route_write_access = require_admin_permission(AdminPermission.routes_write)
require_route_preview_access = require_admin_permission(AdminPermission.routes_preview)
require_user_management_access = require_admin_permission(AdminPermission.users_manage)


def log_bootstrap_result(result: BootstrapAdminResult) -> None:
    if result.generated_password:
        LOGGER.warning(
            "Bootstrapped admin user '%s' with generated password '%s'. Change it immediately after first sign-in.",
            result.username,
            result.password,
        )
        return

    if result.weak_password:
        LOGGER.warning(
            "Bootstrapped admin user '%s' from legacy short bootstrap credentials. Change it immediately after first sign-in.",
            result.username,
        )
        return

    LOGGER.warning(
        "Bootstrapped admin user '%s' from configured bootstrap credentials. Change it immediately after first sign-in.",
        result.username,
    )
