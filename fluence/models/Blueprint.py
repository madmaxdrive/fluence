from marshmallow import Schema, fields
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .Account import AccountSchema
from .Base import Base


class Blueprint(Base):
    __tablename__ = 'blueprint'

    id = Column(Integer, primary_key=True)
    permanent_id = Column(String, unique=True)
    minter_id = Column(Integer, ForeignKey('account.id'), nullable=False)
    expire_at = Column(DateTime(timezone=True))

    minter = relationship('Account')
    contract = relationship('Contract', back_populates='blueprint')


class BlueprintSchema(Schema):
    permanent_id = fields.String()
    minter = fields.Nested(AccountSchema())
    expire_at = fields.DateTime()
