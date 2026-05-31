"""add proxy_instance roles (standalone/frontend + backend_tunnel_ip)

Revision ID: 20261003
Revises: 20261002
Create Date: 2026-10-03

"""
from alembic import op
import sqlalchemy as sa


revision = "20261003"
down_revision = "20261002"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("proxy_instances") as batch_op:
        batch_op.add_column(sa.Column("role", sa.String(20), nullable=False, server_default="standalone"))
        batch_op.add_column(sa.Column("backend_tunnel_ip", sa.String(64), nullable=True))


def downgrade():
    with op.batch_alter_table("proxy_instances") as batch_op:
        batch_op.drop_column("backend_tunnel_ip")
        batch_op.drop_column("role")
