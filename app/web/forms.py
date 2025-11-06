from pydantic import BaseModel, Field


class SerialSettingsForm(BaseModel):
    serial_port: str | None = Field(default=None)
    baud_rate: int = Field(default=9600)
    parity: str = Field(default="N")
    stop_bits: float = Field(default=1.0)


class AudioSettingsForm(BaseModel):
    audio_device: str | None = Field(default=None)

