from pathlib import Path
from typing import Optional

from pydantic import BaseModel


class Settings(BaseModel):
    """Application configuration container."""

    database_path: Path = Path("data/app.db")
    ffmpeg_path: str = "ffmpeg"
    default_serial_baud_rate: int = 9600
    default_serial_parity: str = "N"
    default_serial_stop_bits: float = 1.0
    audio_probe_timeout: float = 2.0

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.database_path}"


settings = Settings()


def ensure_directories(settings_obj: Optional[Settings] = None) -> None:
    """Create required directories if they do not exist yet."""

    current_settings = settings_obj or settings
    current_settings.database_path.parent.mkdir(parents=True, exist_ok=True)

