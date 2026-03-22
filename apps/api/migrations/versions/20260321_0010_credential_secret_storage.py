"""Split connection config into settings plus encrypted credential secrets.

Revision ID: 20260321_0010
Revises: 20260319_0009
Create Date: 2026-03-21 05:10:00.000000
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from alembic import op
from cryptography.fernet import Fernet, InvalidToken
import sqlalchemy as sa

from app.config import Settings


revision = "20260321_0010"
down_revision = "20260319_0009"
branch_labels = None
depends_on = None

_POSTGRES_SECRET_KEYS = ("dsn", "database_url", "url", "password")


def _derive_fernet_key(seed: str) -> bytes:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(digest)


def _build_fernet() -> Fernet:
    settings = Settings()
    configured_key = str(settings.credential_encryption_key or "").strip()
    if not configured_key:
        raise RuntimeError(
            "CREDENTIAL_ENCRYPTION_KEY must be configured before running the credential secret storage migration."
        )
    try:
        return Fernet(configured_key.encode("utf-8"))
    except ValueError:
        return Fernet(_derive_fernet_key(configured_key))


def _ensure_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return dict(parsed) if isinstance(parsed, dict) else {}
    return {}


def _split_config(connector_type: str, config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    settings = dict(config)
    secret_material: dict[str, Any] = {}
    normalized_type = str(connector_type or "").strip().lower()

    if normalized_type == "http":
        headers = settings.pop("headers", None)
        if isinstance(headers, dict) and headers:
            secret_material["headers"] = {
                str(key): str(value)
                for key, value in headers.items()
                if value not in {None, ""}
            }
            if not secret_material["headers"]:
                secret_material.pop("headers", None)
        return settings, secret_material

    if normalized_type == "postgres":
        for key in _POSTGRES_SECRET_KEYS:
            value = settings.pop(key, None)
            if value in {None, ""}:
                continue
            secret_material[key] = str(value)
        return settings, secret_material

    return settings, {}


def _merge_config(settings: dict[str, Any], secret_material: dict[str, Any]) -> dict[str, Any]:
    merged = dict(settings)
    headers = secret_material.get("headers")
    if isinstance(headers, dict) and headers:
        merged["headers"] = dict(headers)
    for key in _POSTGRES_SECRET_KEYS:
        value = secret_material.get(key)
        if value in {None, ""}:
            continue
        merged[key] = str(value)
    return merged


def _encrypt_payload(fernet: Fernet, payload: dict[str, Any]) -> str:
    serialized = json.dumps(payload, separators=(",", ":"), sort_keys=True, default=str)
    return fernet.encrypt(serialized.encode("utf-8")).decode("utf-8")


def _decrypt_payload(fernet: Fernet, token: str) -> dict[str, Any]:
    try:
        raw = fernet.decrypt(token.encode("utf-8"))
    except InvalidToken as exc:
        raise RuntimeError(
            "Unable to decrypt credential secret material during downgrade. "
            "Re-run the migration with the original CREDENTIAL_ENCRYPTION_KEY."
        ) from exc
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Credential secret material is not valid JSON during downgrade. "
            "Do not continue until the encrypted payload is repaired."
        ) from exc
    return parsed if isinstance(parsed, dict) else {}


def upgrade() -> None:
    op.add_column("connection", sa.Column("settings", sa.JSON(), nullable=True))
    op.add_column("connection", sa.Column("secret_material_encrypted", sa.Text(), nullable=True))

    bind = op.get_bind()
    fernet = _build_fernet()
    rows = bind.execute(
        sa.text("SELECT id, connector_type, config FROM connection")
    ).mappings().all()

    connection_table = sa.table(
        "connection",
        sa.column("id", sa.Integer()),
        sa.column("settings", sa.JSON()),
        sa.column("secret_material_encrypted", sa.Text()),
    )
    for row in rows:
        config = _ensure_dict(row.get("config"))
        settings, secret_material = _split_config(str(row.get("connector_type") or ""), config)
        bind.execute(
            connection_table.update()
            .where(connection_table.c.id == int(row["id"]))
            .values(
                settings=settings,
                secret_material_encrypted=(_encrypt_payload(fernet, secret_material) if secret_material else None),
            )
        )

    with op.batch_alter_table("connection") as batch_op:
        batch_op.drop_column("config")


def downgrade() -> None:
    op.add_column("connection", sa.Column("config", sa.JSON(), nullable=True))

    bind = op.get_bind()
    fernet = _build_fernet()
    rows = bind.execute(
        sa.text("SELECT id, settings, secret_material_encrypted FROM connection")
    ).mappings().all()

    connection_table = sa.table(
        "connection",
        sa.column("id", sa.Integer()),
        sa.column("config", sa.JSON()),
    )
    for row in rows:
        settings = _ensure_dict(row.get("settings"))
        encrypted = str(row.get("secret_material_encrypted") or "").strip()
        secret_material = _decrypt_payload(fernet, encrypted) if encrypted else {}
        config = _merge_config(settings, secret_material)
        bind.execute(
            connection_table.update()
            .where(connection_table.c.id == int(row["id"]))
            .values(config=config)
        )

    with op.batch_alter_table("connection") as batch_op:
        batch_op.drop_column("secret_material_encrypted")
        batch_op.drop_column("settings")
