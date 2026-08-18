"""add model call time to first token

Revision ID: 20260818_0001
Revises: 20260726_0001
Create Date: 2026-08-18 12:12:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20260818_0001"
down_revision: Union[str, Sequence[str], None] = "20260726_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "model_calls",
        sa.Column("ttft_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("model_calls", "ttft_ms")
