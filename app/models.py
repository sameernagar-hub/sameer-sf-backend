from datetime import datetime, timezone
import enum

from sqlalchemy import Boolean, DateTime, Enum as SAEnum, ForeignKey, Index, Integer, String, Text, false, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class AddressType(str, enum.Enum):
    """Supported labels for a contact address."""

    HOME = "Home"
    WORK = "Work"
    OTHER = "Other"


class Address(Base):
    __tablename__ = "addresses"
    __table_args__ = (
        Index(
            "uq_contact_primary_address",
            "contact_id",
            unique=True,
            sqlite_where=text("is_primary = 1"),
            postgresql_where=text("is_primary"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    type: Mapped[AddressType] = mapped_column(
        SAEnum(AddressType, native_enum=False, length=10),
        default=AddressType.HOME,
        nullable=False,
    )
    street: Mapped[str | None] = mapped_column(String(300))
    city: Mapped[str | None] = mapped_column(String(120))
    state: Mapped[str | None] = mapped_column(String(120))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    country: Mapped[str | None] = mapped_column(String(120))
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False, server_default=false(), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    contact: Mapped["Contact"] = relationship(back_populates="addresses")


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    first_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    last_name: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(40))

    company: Mapped[str | None] = mapped_column(String(200))
    job_title: Mapped[str | None] = mapped_column(String(200))

    # Base64 `data:` URL. The default database is in-memory and there is no
    # object store, so the image rides along with the contact.
    photo: Mapped[str | None] = mapped_column(Text)

    notes: Mapped[str | None] = mapped_column(Text)
    addresses: Mapped[list[Address]] = relationship(
        back_populates="contact",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="Address.position",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=_utcnow,
        onupdate=_utcnow,
        server_default=func.now(),
        nullable=False,
    )

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}".strip()

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<Contact id={self.id} email={self.email!r}>"
