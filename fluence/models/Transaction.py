from sqlalchemy import Column, Integer, String, JSON, ForeignKey
from sqlalchemy.orm import relationship
from .Base import Base

TYPE_DEPLOY = 'DEPLOY'


class Transaction(Base):
    __tablename__ = 'transaction'

    id = Column(Integer, primary_key=True)
    hash = Column(String, unique=True, nullable=False)
    block_number = Column(Integer, ForeignKey('block.id'), nullable=False)
    transaction_index = Column(Integer, nullable=False)
    type = Column(String, nullable=False)
    contract_id = Column(Integer, ForeignKey('contract.id'), nullable=False)
    entry_point_selector = Column(String)
    entry_point_type = Column(String)
    calldata = Column(JSON, nullable=False)

    block = relationship('Block', back_populates='transactions')
    contract = relationship('Contract', back_populates='transactions')
