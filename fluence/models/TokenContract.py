from marshmallow import Schema, fields
from sqlalchemy import Column, Integer, Boolean, String, ForeignKey
from sqlalchemy.orm import relationship
from .Base import Base
from .Blueprint import BlueprintSchema

KIND_ERC20 = 1
KIND_ERC721 = 2


class TokenContract(Base):
    __tablename__ = 'token_contract'

    id = Column(Integer, primary_key=True)
    address = Column(String, unique=True, nullable=False)
    fungible = Column(Boolean, nullable=False)
    blueprint_id = Column(Integer, ForeignKey('blueprint.id'), unique=True)
    name = Column(String)
    symbol = Column(String)
    decimals = Column(Integer)
    base_uri = Column(String)
    image = Column(String)

    blueprint = relationship('Blueprint', back_populates='contract', uselist=False)
    tokens = relationship('Token', back_populates='contract')


class TokenContractSchema(Schema):
    address = fields.String()
    fungible = fields.Boolean()
    blueprint = fields.Nested(BlueprintSchema())
    name = fields.String()
    symbol = fields.String()
    decimals = fields.Integer()
    image = fields.String()
