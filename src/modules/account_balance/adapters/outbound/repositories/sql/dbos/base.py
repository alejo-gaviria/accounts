"""Shared SQLAlchemy declarative base for this module's DBOs (Database
Objects). Every ORM model in `dbos/` inherits from this `Base`, not
from a fresh `DeclarativeBase` of its own, so they all register onto
the same `MetaData`/table registry.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
