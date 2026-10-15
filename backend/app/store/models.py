from datetime import UTC, datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Take(Base):
    __tablename__ = "takes"
    __table_args__ = (Index("ix_takes_board", "song_id", "difficulty", "integrity_status", "total"),)

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    song_id: Mapped[str] = mapped_column(String(64), index=True)
    client_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    integrity_status: Mapped[str] = mapped_column(String(10), default="ok")
    player: Mapped[str] = mapped_column(String(24))
    difficulty: Mapped[str] = mapped_column(String(8))
    total: Mapped[int] = mapped_column(Integer)
    grade: Mapped[str] = mapped_column(String(2))
    result_json: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Player(Base):
    __tablename__ = "players"

    client_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    nickname: Mapped[str] = mapped_column(String(24))
    avatar: Mapped[str] = mapped_column(Text, default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC)
    )


class Challenge(Base):
    __tablename__ = "challenges"

    id: Mapped[str] = mapped_column(String(6), primary_key=True)
    take_id: Mapped[str] = mapped_column(String(32), unique=True)
    song_id: Mapped[str] = mapped_column(String(64))
    difficulty: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))


class Rival(Base):
    __tablename__ = "challenge_rivals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    challenge_id: Mapped[str] = mapped_column(String(6), index=True)
    take_id: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
