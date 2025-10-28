from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for SQLAlchemy models."""


class Channel(Base):
    __tablename__ = "channels"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    external_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    rss_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )
    last_polled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    videos: Mapped[list["Video"]] = relationship(back_populates="channel", cascade="all, delete-orphan")
    subscriber_channels: Mapped[list["SubscriberChannel"]] = relationship(
        back_populates="channel", cascade="all, delete-orphan"
    )


class Video(Base):
    __tablename__ = "videos"
    __table_args__ = (UniqueConstraint("channel_id", "youtube_id", name="uq_video_channel_youtube"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    youtube_id: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_lang: Mapped[str | None] = mapped_column(String(16), nullable=True)
    fetched_transcript_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    transcript_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_ready_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    channel: Mapped[Channel] = relationship(back_populates="videos")
    summary: Mapped["Summary" | None] = relationship(back_populates="video", cascade="all, delete-orphan")
    notification_jobs: Mapped[list["NotificationJob"]] = relationship(
        back_populates="video", cascade="all, delete-orphan"
    )


class Summary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), unique=True, nullable=False)
    tl_dr: Mapped[str] = mapped_column(Text, nullable=False)
    highlights: Mapped[str | None] = mapped_column(Text, nullable=True)
    key_quote: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary_status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    summary_retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    summary_last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    video: Mapped[Video] = relationship(back_populates="summary")


class Subscriber(Base):
    __tablename__ = "subscribers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    channels: Mapped[list["SubscriberChannel"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )
    notification_jobs: Mapped[list["NotificationJob"]] = relationship(
        back_populates="subscriber", cascade="all, delete-orphan"
    )


class SubscriberChannel(Base):
    __tablename__ = "subscriber_channels"
    __table_args__ = (UniqueConstraint("subscriber_id", "channel_id", name="uq_subscriber_channel"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False)
    channel_id: Mapped[int] = mapped_column(ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    subscriber: Mapped[Subscriber] = relationship(back_populates="channels")
    channel: Mapped[Channel] = relationship(back_populates="subscriber_channels")


class NotificationJob(Base):
    __tablename__ = "notification_jobs"
    __table_args__ = (UniqueConstraint("video_id", "subscriber_id", name="uq_notification_video_subscriber"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    video_id: Mapped[int] = mapped_column(ForeignKey("videos.id", ondelete="CASCADE"), nullable=False)
    subscriber_id: Mapped[int] = mapped_column(ForeignKey("subscribers.id", ondelete="CASCADE"), nullable=False)
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False)
    retry_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )

    video: Mapped[Video] = relationship(back_populates="notification_jobs")
    subscriber: Mapped[Subscriber] = relationship(back_populates="notification_jobs")
