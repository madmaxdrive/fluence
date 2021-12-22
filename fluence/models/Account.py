from marshmallow import Schema, fields
from sqlalchemy import Column, Integer, Numeric, String
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import relationship
from web3 import Web3

from .Base import Base


class Account(Base):
    __tablename__ = 'account'

    id = Column(Integer, primary_key=True)
    stark_key = Column(Numeric(precision=80), nullable=False)
    _address = Column('address', String, unique=True)

    tokens = relationship('Token', back_populates='owner')

    @hybrid_property
    def address(self):
        return self._address

    @address.setter
    def address(self, address):
        self._address = Web3.toChecksumAddress(address)


class AccountSchema(Schema):
    stark_key = fields.String()
    address = fields.String()
