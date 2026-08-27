from sqlalchemy import create_engine, inspect, text

from app.database import _ensure_contact_photo_column


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
