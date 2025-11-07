from datetime import datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class AppSettings(SQLModel, table=True):
    id: int | None = Field(default=1, primary_key=True)
    serial_port: Optional[str] = Field(default=None, index=True)
    baud_rate: int = Field(default=9600)
    parity: str = Field(default="N", max_length=1)
    stop_bits: float = Field(default=1.0)
    audio_device: Optional[str] = Field(default=None)
    audio_playback_device: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow, nullable=False)
    updated_at: datetime = Field(
        default_factory=datetime.utcnow,
        nullable=False,
        sa_column_kwargs={"onupdate": datetime.utcnow},
    )
