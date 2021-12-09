from sqlalchemy import Column, Integer, String
from sqlalchemy.orm import relationship
from .Base import Base


class Contract(Base):
    __tablename__ = 'contract'

    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False)

    transactions = relationship('Transaction', back_populates='contract')
