from sqlalchemy import Column, Integer, String, DateTime, JSON
from sqlalchemy.orm import relationship
from .Base import Base


class Block(Base):
    __tablename__ = 'block'

    id = Column(Integer, primary_key=True, autoincrement=False)
    hash = Column(String, unique=True, nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False)
    _document = Column(JSON, nullable=False)

    transactions = relationship('Transaction', back_populates='block')
