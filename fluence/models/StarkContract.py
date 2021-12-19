from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from .Base import Base


class StarkContract(Base):
    __tablename__ = 'stark_contract'

    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False)
    block_counter = Column(Integer)

    transactions = relationship('Transaction', back_populates='contract')
