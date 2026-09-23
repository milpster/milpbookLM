"""
STD-01: widen the artifacts.status check constraint to the full lifecycle.

Revision ID: 0009_std_01
Revises: 0008_rsr_01b

The baseline constraint only admitted ('draft', 'ready', 'out_of_date'); the
artifact framework (guide/13, ARCH-13-002) drives one generation pass over the
logical row through draft -> generating -> validating -> ready|failed|cancelled.
This revision widens ck_artifacts_status to the full state set. It is additive
and idempotent (a fresh database whose 0001 create_all already built the final
live-metadata shape converges with a genuine 0008->0009 upgrade), and it is
reversible: the downgrade restores the original narrower constraint.
"""

from alembic import op

revision = "0009_std_01"
down_revision = "0008_rsr_01b"
branch_labels = None
depends_on = None

_FULL_STATUS = (
    "CHECK (status IN ('draft', 'generating', 'validating', 'ready', 'failed', "
    "'cancelled', 'out_of_date'))"
)
_LEGACY_STATUS = "CHECK (status IN ('draft', 'ready', 'out_of_date'))"


def upgrade() -> None:
    """Widen ck_artifacts_status to the full lifecycle state set."""
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS ck_artifacts_status")
    op.execute(f"ALTER TABLE artifacts ADD CONSTRAINT ck_artifacts_status {_FULL_STATUS}")


def downgrade() -> None:
    """Restore the original narrower status constraint (only draft/ready/out_of_date)."""
    op.execute("ALTER TABLE artifacts DROP CONSTRAINT IF EXISTS ck_artifacts_status")
    op.execute(f"ALTER TABLE artifacts ADD CONSTRAINT ck_artifacts_status {_LEGACY_STATUS}")
