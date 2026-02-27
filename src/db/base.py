"""SQLAlchemy declarative base — imported by all model modules."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Project-wide declarative base.

    All ORM models inherit from this class so Alembic can discover them via
    ``target_metadata = Base.metadata`` in the migration environment.
    """
