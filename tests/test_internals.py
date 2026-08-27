import asyncio
from types import SimpleNamespace

from sqlalchemy.dialects import postgresql
from sqlalchemy.pool import StaticPool

from app import crud, database, main, photo as photo_module
from app.models import Contact
from app.photo import _has_valid_image_structure, validate_photo
from app.seed import seed_if_empty


def _data_url(media_type: str, header: bytes) -> str:
    import base64

    return f"data:{media_type};base64,{base64.b64encode(header).decode()}"


def test_model_full_name_strips_missing_side():
    contact = Contact(first_name="Ada", last_name="", email="ada@example.com")

    assert contact.full_name == "Ada"


def test_engine_kwargs_cover_sqlite_memory_file_and_other_dialects():
    memory = database._engine_kwargs("sqlite+pysqlite:///:memory:")
    file_db = database._engine_kwargs("sqlite+pysqlite:///./contacts.db")

    assert memory["poolclass"] is StaticPool
    assert file_db == {"connect_args": {"check_same_thread": False}}
    assert database._engine_kwargs("postgresql+psycopg://localhost/db") == {}


def test_foreign_key_hook_ignores_non_sqlite(monkeypatch):
    fake_engine = SimpleNamespace(dialect=SimpleNamespace(name="postgresql"))
    fake_connection = SimpleNamespace(cursor=lambda: (_ for _ in ()).throw(AssertionError("cursor not needed")))

    monkeypatch.setattr(database, "engine", fake_engine)

    database._enable_sqlite_foreign_keys(fake_connection, None)


def test_crud_falls_back_to_id_for_invalid_sort(client, payload):
    with database.SessionLocal() as db:
        crud.create_contact(db, crud.ContactCreate(**payload))
        items, total = crud.list_contacts(db, sort_by="not_a_column")

    assert total == 1
    assert items[0].id == 1


def test_address_replacement_locks_parent_on_transactional_databases():
    class Result:
        def scalar_one(self):
            return None

    class FakeDb:
        bind = SimpleNamespace(dialect=postgresql.dialect())

        def __init__(self):
            self.executions = []

        def execute(self, statement, **kwargs):
            self.executions.append((statement, kwargs))
            return Result()

        def flush(self):
            self.flushed = True

        def expire(self, contact, fields):
            self.expired = (contact, fields)

    contact = Contact(id=7, first_name="Ada", last_name="Lovelace", email="ada@example.com")
    fake_db = FakeDb()

    crud._replace_addresses(fake_db, contact, [])

    assert len(fake_db.executions) == 2
    assert "FOR UPDATE" in str(fake_db.executions[0][0].compile(dialect=fake_db.bind.dialect))
    assert fake_db.flushed is True
    assert fake_db.expired == (contact, ["addresses"])
    assert contact.updated_at is not None


def test_photo_accepts_supported_raster_signatures():
    assert validate_photo(_data_url("image/jpeg", b"\xff\xd8\xffavatar\xff\xd9")) is not None
    assert validate_photo(_data_url("image/gif", b"GIF89a0000000;")) is not None
    assert validate_photo(_data_url("image/webp", b"RIFF\x08\x00\x00\x00WEBPVP8 ")) is not None


def test_photo_rejects_invalid_base64_payload():
    try:
        validate_photo("data:image/png;base64,AAAAA")
    except ValueError as exc:
        assert "not valid base64" in str(exc)
    else:
        raise AssertionError("invalid base64 was accepted")


def test_photo_rejects_decoded_payload_over_limit(monkeypatch):
    monkeypatch.setattr(photo_module, "MAX_PHOTO_BYTES", 1)
    monkeypatch.setattr(photo_module, "_MAX_ENCODED_LENGTH", 100)

    try:
        validate_photo(_data_url("image/png", b"\x89PNG\r\n\x1a\n"))
    except ValueError as exc:
        assert "maximum size" in str(exc)
    else:
        raise AssertionError("oversized decoded image was accepted")


def test_photo_rejects_signature_only_jpeg_gif_and_webp():
    for media_type, data in [
        ("image/jpeg", b"\xff\xd8\xff"),
        ("image/gif", b"GIF89a"),
        ("image/webp", b"RIFFxxxxWEBP"),
    ]:
        try:
            validate_photo(_data_url(media_type, data))
        except ValueError as exc:
            assert "not a valid" in str(exc)
        else:
            raise AssertionError(f"truncated {media_type} was accepted")


def test_photo_structure_guard_rejects_unknown_media_type():
    assert _has_valid_image_structure(b"anything", "image/avif") is False


def test_seed_if_empty_adds_samples_once(client):
    assert seed_if_empty() == 3
    assert seed_if_empty() == 0

    response = client.get("/api/v1/contacts")
    assert response.json()["total"] == 3
    assert len(response.json()["items"][0]["addresses"]) == 2


def test_lifespan_logs_when_seed_adds_rows(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(main.settings, "seed_data", True)
    monkeypatch.setattr(main, "init_db", lambda: events.append(("init", None)))
    monkeypatch.setattr(main, "seed_if_empty", lambda: 3)
    monkeypatch.setattr(main.logger, "info", lambda message, value: events.append((message, value)))
    monkeypatch.setattr(main.engine, "dispose", lambda: events.append(("dispose", None)))

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            events.append(("inside", None))

    asyncio.run(run_lifespan())

    assert ("seeded %d sample contacts", 3) in events
    assert ("inside", None) in events
    assert ("dispose", None) in events


def test_lifespan_skips_seed_log_when_no_rows_added(monkeypatch):
    events: list[tuple[str, object]] = []

    monkeypatch.setattr(main.settings, "seed_data", True)
    monkeypatch.setattr(main, "init_db", lambda: events.append(("init", None)))
    monkeypatch.setattr(main, "seed_if_empty", lambda: 0)
    monkeypatch.setattr(main.logger, "info", lambda message, value: events.append((message, value)))
    monkeypatch.setattr(main.engine, "dispose", lambda: events.append(("dispose", None)))

    async def run_lifespan() -> None:
        async with main.lifespan(main.app):
            events.append(("inside", None))

    asyncio.run(run_lifespan())

    assert ("seeded %d sample contacts", 0) not in events
    assert ("inside", None) in events
