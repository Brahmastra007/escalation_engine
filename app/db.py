from datetime import datetime, timezone

from sqlalchemy import String, Text, DateTime, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class Ticket(Base):
    __tablename__ = "tickets"

    ticket_id: Mapped[str] = mapped_column(String, primary_key=True)
    customer_email: Mapped[str] = mapped_column(String, nullable=False)
    ticket_content: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String, nullable=False, default="")
    proposed_action: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String, nullable=False, default="processing")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc)
    )


_SessionLocal: sessionmaker | None = None


def get_db():
    """FastAPI dependency — yields a session per request, closes it when done."""
    session = _SessionLocal()
    try:
        yield session
    finally:
        session.close()


def get_session():
    """For use in background tasks (outside request lifecycle). Caller must close or use as context manager."""
    return _SessionLocal()


def init_db(database_url: str):
    """Create the engine, bind the session factory, and create tables if they don't exist."""
    global _SessionLocal
    # SQLAlchemy needs the +psycopg suffix to use psycopg v3 instead of the legacy psycopg2.
    sa_url = database_url.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_engine(sa_url)
    _SessionLocal = sessionmaker(engine)
    Base.metadata.create_all(engine)
