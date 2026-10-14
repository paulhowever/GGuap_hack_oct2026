from datetime import UTC, datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Take(Base):
    __tablename__ = "takes"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    song_id: Mapped[str] = mapped_column(String(64), index=True)
    player: Mapped[str] = mapped_column(String(24))
    difficulty: Mapped[str] = mapped_column(String(8))
    total: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(2))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
