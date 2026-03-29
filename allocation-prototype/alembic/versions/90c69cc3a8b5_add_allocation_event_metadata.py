"""add allocation event metadata

Revision ID: 90c69cc3a8b5
Revises: 13cab1c6d55d
Create Date: 2026-03-30 01:16:12.711289

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '90c69cc3a8b5'
down_revision: Union[str, Sequence[str], None] = '13cab1c6d55d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("allocation_events") as batch_op:
        batch_op.add_column(sa.Column("trace_hash", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("config_version_hash", sa.String(length=64), nullable=True))
        batch_op.create_index(
            batch_op.f("ix_allocation_events_config_version_hash"),
            ["config_version_hash"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_allocation_events_trace_hash"),
            ["trace_hash"],
            unique=False,
        )

    op.execute(
        """
        UPDATE allocation_events
        SET
            trace_hash = (
                SELECT sealed_manifests.trace_hash
                FROM sealed_manifests
                WHERE sealed_manifests.manifest_id = allocation_events.manifest_id
            ),
            config_version_hash = (
                SELECT sealed_manifests.config_version_hash
                FROM sealed_manifests
                WHERE sealed_manifests.manifest_id = allocation_events.manifest_id
            )
        """
    )

    with op.batch_alter_table("allocation_events") as batch_op:
        batch_op.alter_column("trace_hash", existing_type=sa.String(length=64), nullable=False)
        batch_op.alter_column("config_version_hash", existing_type=sa.String(length=64), nullable=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("allocation_events") as batch_op:
        batch_op.drop_index(batch_op.f("ix_allocation_events_trace_hash"))
        batch_op.drop_index(batch_op.f("ix_allocation_events_config_version_hash"))
        batch_op.drop_column("config_version_hash")
        batch_op.drop_column("trace_hash")
