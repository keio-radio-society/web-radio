from collections.abc import Iterator
from typing import cast

from fastapi import Depends, Request, WebSocket
from sqlmodel import Session

from .db import engine
from .serial.service import SerialService
from .audio.streamer import SoundDeviceStreamer


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session


SessionDep = Depends(get_session)


def _get_app(request: Request = None, websocket: WebSocket = None):
    scope = request or websocket
    if scope is None:
        raise RuntimeError("Request/WebSocket scope is required.")
    return scope.app  # type: ignore[attr-defined]


def get_serial_service(
    request: Request = None,
    websocket: WebSocket = None,
) -> SerialService:
    app = _get_app(request, websocket)
    return cast(SerialService, app.state.serial_service)


def get_audio_streamer(
    request: Request = None,
    websocket: WebSocket = None,
) -> SoundDeviceStreamer:
    app = _get_app(request, websocket)
    return cast(SoundDeviceStreamer, app.state.audio_streamer)
