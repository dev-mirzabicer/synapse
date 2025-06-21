"""Add provider configuration to group members"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = 'addprovider0001'
down_revision: Union[str, Sequence[str], None] = 'bf5e249d927f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('group_members', sa.Column('provider', sa.String(length=50), nullable=False, server_default='openai'))
    op.add_column('group_members', sa.Column('model', sa.String(length=100), nullable=False, server_default='gpt-4o'))
    op.add_column('group_members', sa.Column('temperature', sa.Float(), nullable=False, server_default='0.1'))
    op.alter_column('group_members', 'provider', server_default=None)
    op.alter_column('group_members', 'model', server_default=None)
    op.alter_column('group_members', 'temperature', server_default=None)


def downgrade() -> None:
    op.drop_column('group_members', 'temperature')
    op.drop_column('group_members', 'model')
    op.drop_column('group_members', 'provider')
