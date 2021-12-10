from sqlalchemy import Column, Integer, Numeric, ForeignKey
from sqlalchemy.orm import relationship
from .Base import Base


class Token(Base):
    __tablename__ = 'token'

    id = Column(Integer, primary_key=True)
    contract_id = Column(Integer, ForeignKey('token_contract.id'), nullable=False)
    token_id = Column(Numeric(precision=80), nullable=False)
    owner_id = Column(Integer, ForeignKey('account.id'))
    latest_tx_id = Column(Integer, ForeignKey('transaction.id'), nullable=False)
    ask_id = Column(Integer, ForeignKey('limit_order.id'))

    contract = relationship('TokenContract', back_populates='tokens')
    owner = relationship('Account', back_populates='tokens')
    latest_tx = relationship('Transaction')
    ask = relationship('LimitOrder', foreign_keys=ask_id)
