"""contract blueprint, the.

Revision ID: 4d14bfccc797
Revises: 2d006b2cf180
Create Date: 2021-12-21 13:54:23.389648

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '4d14bfccc797'
down_revision = '2d006b2cf180'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_table('blueprint',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('permanent_id', sa.String(), nullable=True),
    sa.Column('minter_id', sa.Integer(), nullable=False),
    sa.Column('expire_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('token_contract_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['minter_id'], ['account.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('permanent_id')
    )
    op.execute("""
    INSERT INTO blueprint (id, minter_id, token_contract_id)
    SELECT nextval('blueprint_id_seq'), minter_id, id
    FROM token_contract WHERE minter_id IS NOT NULL
    """)
    op.add_column('token_contract', sa.Column('blueprint_id', sa.Integer(), unique=True, nullable=True))
    op.execute("""
    UPDATE token_contract c SET blueprint_id = b.id
    FROM blueprint b WHERE c.id = b.token_contract_id
    """)
    op.drop_constraint('token_contract_minter_id_fkey', 'token_contract', type_='foreignkey')
    op.create_foreign_key(None, 'token_contract', 'blueprint', ['blueprint_id'], ['id'])
    op.drop_column('token_contract', 'minter_id')
    op.drop_column('blueprint', 'token_contract_id')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('token_contract', sa.Column('minter_id', sa.INTEGER(), autoincrement=False, nullable=True))
    op.execute("""
    UPDATE token_contract c SET minter_id = b.minter_id
    FROM blueprint b WHERE c.blueprint_id = b.id
    """)
    op.drop_constraint('token_contract_blueprint_id_fkey', 'token_contract', type_='foreignkey')
    op.create_foreign_key('token_contract_minter_id_fkey', 'token_contract', 'account', ['minter_id'], ['id'])
    op.drop_column('token_contract', 'blueprint_id')
    op.drop_table('blueprint')
    # ### end Alembic commands ###