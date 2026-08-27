from collections.abc import Generator

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def _engine_kwargs(database_url: str) -> dict:
    if not database_url.startswith("sqlite"):
        return {}

    kwargs: dict = {"connect_args": {"check_same_thread": False}}
    if ":memory:" in database_url or "mode=memory" in database_url:
        # A plain in-memory SQLite database lives and dies with its connection.
        # StaticPool keeps a single connection alive so every request — and every
        # thread FastAPI hands work to — sees the same data for the process's lifetime.
        kwargs["poolclass"] = StaticPool
    return kwargs


settings = get_settings()

engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    **_engine_kwargs(settings.database_url),
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


@event.listens_for(Engine, "connect")
def _enable_sqlite_foreign_keys(dbapi_connection, _connection_record) -> None:
    if engine.dialect.name != "sqlite":
        return
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()


def init_db() -> None:
    """Create tables. Called on startup; safe to call repeatedly."""
    from app import models  # noqa: F401  (register models on Base.metadata)

    Base.metadata.create_all(bind=engine)
    _ensure_contact_photo_column(engine)
    _backfill_legacy_addresses(engine)


def _ensure_contact_photo_column(target_engine) -> None:
    """
    Upgrade pre-photo persisted databases before the app serves traffic.

    `create_all()` creates missing tables but does not add columns to an
    existing table. The hackathon default is in-memory and starts fresh, but
    file SQLite and Postgres URLs are supported too, so this keeps older
    databases from failing on the mapped `Contact.photo` column.
    """
    inspector = inspect(target_engine)
    if "contacts" not in inspector.get_table_names():
        return
    if any(column["name"] == "photo" for column in inspector.get_columns("contacts")):
        return

    with target_engine.begin() as connection:
        connection.execute(text("ALTER TABLE contacts ADD COLUMN photo TEXT"))


def _backfill_legacy_addresses(target_engine) -> None:
    """
    Copy pre-0.2 flat address columns into the normalized address table once.

    Older persisted databases may still have `address`, `city`, `state`,
    `postal_code`, and `country` on `contacts`. Current API responses read only
    from `addresses`, so startup preserves non-empty legacy values as one
    primary Home address unless the contact already has child address rows.
    """
    inspector = inspect(target_engine)
    table_names = inspector.get_table_names()
    if "contacts" not in table_names or "addresses" not in table_names:
        return

    contact_columns = {column["name"] for column in inspector.get_columns("contacts")}
    legacy_columns = ("address", "city", "state", "postal_code", "country")
    if not set(legacy_columns).issubset(contact_columns):
        return

    nonblank_checks = " OR ".join(f"NULLIF(TRIM({column}), '') IS NOT NULL" for column in legacy_columns)
    with target_engine.begin() as connection:
        connection.execute(
            text(
                f"""
                INSERT INTO addresses (
                    contact_id, type, street, city, state, postal_code, country, is_primary, position
                )
                SELECT id, :address_type, address, city, state, postal_code, country, :is_primary, 0
                FROM contacts
                WHERE ({nonblank_checks})
                  AND NOT EXISTS (
                      SELECT 1 FROM addresses WHERE addresses.contact_id = contacts.id
                  )
                """
            ),
            {"address_type": "HOME", "is_primary": True},
        )


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency yielding a session that is always closed."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
