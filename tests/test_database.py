from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session

from app import models  # noqa: F401  (register models on Base.metadata)
from app.database import Base, _backfill_legacy_addresses, _ensure_contact_photo_column
from app.models import Contact


def test_startup_upgrade_adds_photo_to_legacy_sqlite_database(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_engine(f"sqlite+pysqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    email VARCHAR(320) NOT NULL UNIQUE
                )
                """
            )
        )

    _ensure_contact_photo_column(engine)
    _ensure_contact_photo_column(engine)

    columns = {column["name"] for column in inspect(engine).get_columns("contacts")}
    assert "photo" in columns


def test_startup_upgrade_is_noop_before_contacts_table_exists(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'empty.db'}")

    _ensure_contact_photo_column(engine)

    assert "contacts" not in inspect(engine).get_table_names()


def test_startup_backfills_legacy_address_columns_once(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy-addresses.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    address VARCHAR(300),
                    city VARCHAR(120),
                    state VARCHAR(120),
                    postal_code VARCHAR(20),
                    country VARCHAR(120)
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO contacts (
                    id, first_name, last_name, email, address, city, state, postal_code, country
                )
                VALUES (1, 'Ada', 'Lovelace', 'ada@example.com', '1 Market St', 'San Francisco', 'CA', '94105', 'USA')
                """
            )
        )
    Base.metadata.create_all(bind=engine)

    _backfill_legacy_addresses(engine)
    _backfill_legacy_addresses(engine)

    with engine.connect() as connection:
        rows = connection.execute(text("SELECT contact_id, type, street, city, is_primary FROM addresses")).all()
    assert rows == [(1, "HOME", "1 Market St", "San Francisco", 1)]


def test_startup_backfilled_addresses_load_through_orm(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'legacy-addresses-orm.db'}")
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE contacts (
                    id INTEGER PRIMARY KEY,
                    first_name VARCHAR(100) NOT NULL,
                    last_name VARCHAR(100) NOT NULL,
                    email VARCHAR(320) NOT NULL UNIQUE,
                    phone VARCHAR(40),
                    company VARCHAR(200),
                    job_title VARCHAR(200),
                    photo TEXT,
                    notes TEXT,
                    address VARCHAR(300),
                    city VARCHAR(120),
                    state VARCHAR(120),
                    postal_code VARCHAR(20),
                    country VARCHAR(120),
                    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
        )
        connection.execute(
            text(
                """
                INSERT INTO contacts (
                    id, first_name, last_name, email, address, city, state, postal_code, country
                )
                VALUES (1, 'Ada', 'Lovelace', 'ada@example.com', '1 Market St', 'San Francisco', 'CA', '94105', 'USA')
                """
            )
        )
    Base.metadata.create_all(bind=engine)

    _backfill_legacy_addresses(engine)

    with Session(engine) as session:
        contact = session.get(Contact, 1)
        assert contact is not None
        assert contact.addresses[0].type.value == "Home"
        assert contact.addresses[0].is_primary is True


def test_startup_backfill_ignores_non_legacy_schema(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'current.db'}")
    Base.metadata.create_all(bind=engine)

    _backfill_legacy_addresses(engine)

    with engine.connect() as connection:
        count = connection.execute(text("SELECT count(*) FROM addresses")).scalar_one()
    assert count == 0


def test_startup_backfill_is_noop_before_tables_exist(tmp_path):
    engine = create_engine(f"sqlite+pysqlite:///{tmp_path / 'empty-addresses.db'}")

    _backfill_legacy_addresses(engine)

    assert inspect(engine).get_table_names() == []
