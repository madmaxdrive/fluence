from marshmallow import Schema, fields
from sqlalchemy import Column, Integer, Numeric, String, JSON, ForeignKey
from sqlalchemy.orm import relationship

from .Base import Base
from .TokenContract import TokenContractSchema


class Token(Base):
    __tablename__ = 'token'

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('token_contract.id'), nullable=False)
    token_id = Column(Numeric(precision=80), nullable=False)
    owner_id = Column(Integer, ForeignKey('account.id'))
    latest_tx_id = Column(Integer, ForeignKey('transaction.id'), nullable=False)
    ask_id = Column(Integer, ForeignKey('limit_order.id'))
    name = Column(String)
    description = Column(String)
    image = Column(String)
    token_uri = Column(String)
    _metadata = Column(JSON)

    contract = relationship('TokenContract', back_populates='tokens')
    owner = relationship('Account', back_populates='tokens')
    latest_tx = relationship('Transaction')
    ask = relationship('LimitOrder', foreign_keys=ask_id, post_update=True)


class TokenSchema(Schema):
    contract = fields.Nested(TokenContractSchema())
    token_id = fields.String()
    name = fields.String()
    description = fields.String()
    image = fields.String()
