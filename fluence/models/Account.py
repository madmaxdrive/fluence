from sqlalchemy import Column, Integer, Numeric, String
from sqlalchemy.orm import relationship
from .Base import Base


class Account(Base):
    __tablename__ = 'account'

    id = Column(Integer, primary_key=True)
    stark_key = Column(Numeric(precision=80), nullable=False)
    address = Column(String)

    tokens = relationship('Token', back_populates='owner')
