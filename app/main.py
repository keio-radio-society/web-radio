from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .audio.streamer import SoundDeviceStreamer
from .audio.playback import PlaybackService
from .serial.service import SerialConfiguration, SerialService
from .db import init_db, session_scope
from .repositories import SettingsRepository
from .webrtc.manager import WebRTCManager
from .web.routes import router as web_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    serial_service = SerialService()
    audio_streamer = SoundDeviceStreamer()
    playback_service = PlaybackService()
    webrtc_manager = WebRTCManager(audio_streamer, playback_service)

    await serial_service.start()
    await audio_streamer.start()
    await playback_service.start()

    with session_scope() as session:
        stored_settings = SettingsRepository(session).get()

    config = SerialConfiguration(
        port=stored_settings.serial_port,
        baud_rate=stored_settings.baud_rate,
        parity=stored_settings.parity,
        stop_bits=stored_settings.stop_bits,
    )

    try:
        await serial_service.apply_configuration(config)
    except Exception as exc:  # pylint: disable=broad-except
        # Serial デバイスが未接続でもアプリは起動できるようにする
        import logging

        logging.getLogger(__name__).warning("Serial configuration failed: %s", exc)

    try:
        await audio_streamer.set_device(stored_settings.audio_device)
    except Exception as exc:  # pylint: disable=broad-except
        import logging

        logging.getLogger(__name__).warning("Audio device configuration failed: %s", exc)

    try:
        await playback_service.set_device(stored_settings.audio_playback_device)
    except Exception as exc:  # pylint: disable=broad-except
        import logging

        logging.getLogger(__name__).warning("Playback device configuration failed: %s", exc)

    app.state.serial_service = serial_service
    app.state.audio_streamer = audio_streamer
    app.state.playback_service = playback_service
    app.state.webrtc_manager = webrtc_manager

    try:
        yield
    finally:
        await webrtc_manager.shutdown()
        await audio_streamer.stop()
        await playback_service.stop()
        await serial_service.stop()


app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="app/web/static"), name="static")

app.include_router(web_router)
