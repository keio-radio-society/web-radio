from collections.abc import Iterator
from typing import TYPE_CHECKING, cast

from fastapi import Depends, Request
from sqlmodel import Session

from .db import engine
from .serial.service import SerialService
from .audio.streamer import AudioStreamer


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Depends(get_session)


def get_serial_service(request: Request) -> SerialService:
    return cast(SerialService, request.app.state.serial_service)


def get_audio_streamer(request: Request) -> AudioStreamer:
    return cast(AudioStreamer, request.app.state.audio_streamer)

