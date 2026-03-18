"""Add runtime platform scaffolding tables.

Revision ID: 20260318_0007
Revises: 20260318_0006
Create Date: 2026-03-18 04:10:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "20260318_0007"
down_revision = "20260318_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "routeimplementation",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_draft", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("flow_definition", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["route_id"], ["endpointdefinition.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routeimplementation_route_id", "routeimplementation", ["route_id"], unique=False)

    op.create_table(
        "routedeployment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("implementation_id", sa.Integer(), nullable=False),
        sa.Column("environment", sa.String(length=64), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("published_at", sa.DateTime(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["implementation_id"], ["routeimplementation.id"]),
        sa.ForeignKeyConstraint(["route_id"], ["endpointdefinition.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_routedeployment_environment", "routedeployment", ["environment"], unique=False)
    op.create_index("ix_routedeployment_implementation_id", "routedeployment", ["implementation_id"], unique=False)
    op.create_index("ix_routedeployment_route_id", "routedeployment", ["route_id"], unique=False)

    op.create_table(
        "connection",
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
    op.create_index("ix_connection_name", "connection", ["name"], unique=True)

    op.create_table(
        "executionrun",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("route_id", sa.Integer(), nullable=False),
        sa.Column("deployment_id", sa.Integer(), nullable=True),
        sa.Column("implementation_id", sa.Integer(), nullable=True),
        sa.Column("environment", sa.String(length=64), nullable=False, server_default="production"),
        sa.Column("method", sa.String(length=16), nullable=False),
        sa.Column("path", sa.String(length=512), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("request_data", sa.JSON(), nullable=True),
        sa.Column("response_status_code", sa.Integer(), nullable=True),
        sa.Column("response_body", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["deployment_id"], ["routedeployment.id"]),
        sa.ForeignKeyConstraint(["implementation_id"], ["routeimplementation.id"]),
        sa.ForeignKeyConstraint(["route_id"], ["endpointdefinition.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_executionrun_deployment_id", "executionrun", ["deployment_id"], unique=False)
    op.create_index("ix_executionrun_implementation_id", "executionrun", ["implementation_id"], unique=False)
    op.create_index("ix_executionrun_route_id", "executionrun", ["route_id"], unique=False)

    op.create_table(
        "executionstep",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("node_id", sa.String(length=128), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="success"),
        sa.Column("input_data", sa.JSON(), nullable=True),
        sa.Column("output_data", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(length=1000), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["executionrun.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_executionstep_run_id", "executionstep", ["run_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_executionstep_run_id", table_name="executionstep")
    op.drop_table("executionstep")

    op.drop_index("ix_executionrun_route_id", table_name="executionrun")
    op.drop_index("ix_executionrun_implementation_id", table_name="executionrun")
    op.drop_index("ix_executionrun_deployment_id", table_name="executionrun")
    op.drop_table("executionrun")

    op.drop_index("ix_connection_name", table_name="connection")
    op.drop_table("connection")

    op.drop_index("ix_routedeployment_route_id", table_name="routedeployment")
    op.drop_index("ix_routedeployment_implementation_id", table_name="routedeployment")
    op.drop_index("ix_routedeployment_environment", table_name="routedeployment")
    op.drop_table("routedeployment")

    op.drop_index("ix_routeimplementation_route_id", table_name="routeimplementation")
    op.drop_table("routeimplementation")
