"""Scope runtime connections by project and environment.

Revision ID: 20260319_0008
Revises: 20260318_0007
Create Date: 2026-03-19 16:20:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260319_0008"
down_revision = "20260318_0007"
branch_labels = None
depends_on = None

DEFAULT_CONNECTION_PROJECT = "default"
DEFAULT_CONNECTION_ENVIRONMENT = "production"


def upgrade() -> None:
    op.create_table(
        "connection_v2",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project", sa.String(length=120), nullable=False, server_default=DEFAULT_CONNECTION_PROJECT),
        sa.Column("environment", sa.String(length=64), nullable=False, server_default=DEFAULT_CONNECTION_ENVIRONMENT),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False, server_default="http"),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project", "environment", "name", name="uq_connection_scope_name"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO connection_v2 (
                id,
                project,
                environment,
                name,
                connector_type,
                description,
                config,
                is_active,
                created_at,
                updated_at
            )
            SELECT
                id,
                :default_project,
                :default_environment,
                name,
                connector_type,
                description,
                config,
                is_active,
                created_at,
                updated_at
            FROM connection
            """
        ).bindparams(
            default_project=DEFAULT_CONNECTION_PROJECT,
            default_environment=DEFAULT_CONNECTION_ENVIRONMENT,
        )
    )
    op.drop_index("ix_connection_name", table_name="connection")
    op.drop_table("connection")
    op.rename_table("connection_v2", "connection")
    op.create_index("ix_connection_environment", "connection", ["environment"], unique=False)
    op.create_index("ix_connection_name", "connection", ["name"], unique=False)
    op.create_index("ix_connection_project", "connection", ["project"], unique=False)

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                SELECT setval(
                    pg_get_serial_sequence('connection', 'id'),
                    COALESCE((SELECT MAX(id) FROM connection), 1),
                    true
                )
                """
            )
        )


def downgrade() -> None:
    bind = op.get_bind()
    duplicate_names = bind.execute(
        sa.text(
            """
            SELECT name
            FROM connection
            GROUP BY name
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()
    if duplicate_names:
        duplicate_list = ", ".join(str(row[0]) for row in duplicate_names)
        raise RuntimeError(
            "Cannot downgrade scoped connections while duplicate names exist across scopes: "
            f"{duplicate_list}"
        )

    op.create_table(
        "connection_legacy",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=160), nullable=False),
        sa.Column("connector_type", sa.String(length=32), nullable=False, server_default="http"),
        sa.Column("description", sa.String(length=500), nullable=True),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name"),
    )
    op.execute(
        sa.text(
            """
            INSERT INTO connection_legacy (
                id,
                name,
                connector_type,
                description,
                config,
                is_active,
                created_at,
                updated_at
            )
            SELECT
                id,
                name,
                connector_type,
                description,
                config,
                is_active,
                created_at,
                updated_at
            FROM connection
            """
        )
    )
    op.drop_index("ix_connection_project", table_name="connection")
    op.drop_index("ix_connection_name", table_name="connection")
    op.drop_index("ix_connection_environment", table_name="connection")
    op.drop_table("connection")
    op.rename_table("connection_legacy", "connection")
    op.create_index("ix_connection_name", "connection", ["name"], unique=True)

    if bind.dialect.name == "postgresql":
        op.execute(
            sa.text(
                """
                SELECT setval(
                    pg_get_serial_sequence('connection', 'id'),
                    COALESCE((SELECT MAX(id) FROM connection), 1),
                    true
                )
                """
            )
        )
