from sqlalchemy import Column, Integer, Boolean, String, ForeignKey
from sqlalchemy.orm import relationship
from .Base import Base

KIND_ERC20 = 1
KIND_ERC721 = 2


class TokenContract(Base):
    __tablename__ = 'token_contract'

    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False)
    fungible = Column(Boolean, nullable=False)

    tokens = relationship('Token', back_populates='contract')
