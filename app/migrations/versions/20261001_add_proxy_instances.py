"""add proxy_instances table and migrate active proxy_keys

Revision ID: 20261001_add_proxy_instances
Revises: None
Create Date: 2026-10-01 12:00:00
"""

from alembic import op
import sqlalchemy as sa
import uuid

revision = "20261001_add_proxy_instances"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "proxy_instances",
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("secret", sa.String(length=256), nullable=False),
        sa.Column("fake_tls_domain", sa.String(length=255), nullable=False, server_default="www.google.com"),
        sa.Column("bind_ip", sa.String(length=64), nullable=False, server_default="0.0.0.0"),
        sa.Column("bind_port", sa.Integer(), nullable=False),
        sa.Column("stats_port", sa.Integer(), nullable=False),
        sa.Column("owner_user_id", sa.Integer(), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_blocked", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("total_traffic", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("traffic_used", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("connection_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_user_id"], ["users.id"]),
        sa.UniqueConstraint("secret", name="uq_proxy_instances_secret"),
        sa.UniqueConstraint("bind_ip", "bind_port", name="uq_proxy_instances_bind"),
        sa.UniqueConstraint("stats_port", name="uq_proxy_instances_stats_port"),
    )

    conn = op.get_bind()
    rows = conn.execute(
        sa.text(
            """
            SELECT id, name, secret, fake_tls_domain, user_id, is_active, is_blocked,
                   total_traffic, traffic_used, connection_count, notes, created_at, updated_at
            FROM proxy_keys
            WHERE is_active = 1 AND is_blocked = 0
            ORDER BY id ASC
            """
        )
    ).fetchall()

    bind_port = 10000
    stats_port = 31000

    for row in rows:
        pid = str(uuid.uuid4())
        conn.execute(
            sa.text(
                """
                INSERT INTO proxy_instances (
                    id, name, secret, fake_tls_domain, bind_ip, bind_port, stats_port,
                    owner_user_id, is_enabled, is_blocked, total_traffic, traffic_used,
                    connection_count, notes, created_at, updated_at
                ) VALUES (
                    :id, :name, :secret, :domain, '0.0.0.0', :bind_port, :stats_port,
                    :owner_user_id, :is_enabled, :is_blocked, :total_traffic, :traffic_used,
                    :connection_count, :notes, :created_at, :updated_at
                )
                """
            ),
            {
                "id": pid,
                "name": row.name,
                "secret": row.secret,
                "domain": row.fake_tls_domain or "www.google.com",
                "bind_port": bind_port,
                "stats_port": stats_port,
                "owner_user_id": row.user_id,
                "is_enabled": bool(row.is_active),
                "is_blocked": bool(row.is_blocked),
                "total_traffic": row.total_traffic or 0,
                "traffic_used": row.traffic_used or 0,
                "connection_count": row.connection_count or 0,
                "notes": row.notes,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            },
        )
        bind_port += 1
        stats_port += 1


def downgrade():
    op.drop_table("proxy_instances")