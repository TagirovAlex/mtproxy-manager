"""add limits to proxy_instances

Revision ID: 20261002_add_proxy_instance_limits
Revises: 20261001_add_proxy_instances
Create Date: 2026-10-02 10:00:00
"""

from alembic import op
import sqlalchemy as sa

revision = "20261002_add_proxy_instance_limits"
down_revision = "20261001_add_proxy_instances"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("proxy_instances", sa.Column("traffic_limit_bytes", sa.BigInteger(), nullable=True))
    op.add_column("proxy_instances", sa.Column("traffic_limit_period", sa.String(length=10), nullable=True, server_default="none"))
    op.add_column("proxy_instances", sa.Column("period_started_at", sa.DateTime(), nullable=True))
    op.add_column("proxy_instances", sa.Column("period_baseline_bytes", sa.BigInteger(), nullable=True, server_default="0"))
    op.add_column("proxy_instances", sa.Column("period_used_bytes", sa.BigInteger(), nullable=True, server_default="0"))
    op.add_column("proxy_instances", sa.Column("paused_by_limit", sa.Boolean(), nullable=True, server_default=sa.text("0")))
    op.add_column("proxy_instances", sa.Column("limit_exceeded_at", sa.DateTime(), nullable=True))


def downgrade():
    op.drop_column("proxy_instances", "limit_exceeded_at")
    op.drop_column("proxy_instances", "paused_by_limit")
    op.drop_column("proxy_instances", "period_used_bytes")
    op.drop_column("proxy_instances", "period_baseline_bytes")
    op.drop_column("proxy_instances", "period_started_at")
    op.drop_column("proxy_instances", "traffic_limit_period")
    op.drop_column("proxy_instances", "traffic_limit_bytes")