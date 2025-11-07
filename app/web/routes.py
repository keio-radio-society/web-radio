import logging
from urllib.parse import quote_plus, unquote_plus

from fastapi import APIRouter, Depends, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from ..audio.streamer import SoundDeviceStreamer
from ..dependencies import get_audio_streamer, get_serial_service, get_session
from ..repositories import SettingsRepository
from ..serial.service import SerialConfiguration, SerialService

logger = logging.getLogger(__name__)

templates = Jinja2Templates(directory="app/web/templates")

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="index")
async def index(
    request: Request,
    session=Depends(get_session),
    audio_streamer: SoundDeviceStreamer = Depends(get_audio_streamer),
) -> HTMLResponse:
    settings = SettingsRepository(session).get()
    serial_ports = SerialService.available_ports()
    raw_message = request.query_params.get("msg")
    message = unquote_plus(raw_message) if raw_message else None

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "settings": settings,
            "serial_ports": serial_ports,
            "message": message,
            "audio_ws_url": request.url_for("audio_ws"),
            "audio_sample_rate": audio_streamer._sample_rate,  # type: ignore[attr-defined]  # pylint: disable=protected-access
            "audio_worklet_url": request.url_for(
                "static", path="js/audio-worklet-processor.js"
            ),
        },
    )


@router.get("/settings", response_class=HTMLResponse)
async def settings_page(
    request: Request,
    session=Depends(get_session),
    audio_streamer: SoundDeviceStreamer = Depends(get_audio_streamer),
) -> HTMLResponse:
    settings = SettingsRepository(session).get()
    serial_ports = SerialService.available_ports()
    audio_devices = audio_streamer.available_devices()
    raw_message = request.query_params.get("msg")
    message = unquote_plus(raw_message) if raw_message else None

    return templates.TemplateResponse(
        "settings.html",
        {
            "request": request,
            "settings": settings,
            "serial_ports": serial_ports,
            "audio_devices": audio_devices,
            "parity_options": ["N", "E", "O", "M", "S"],
            "stop_bit_options": [1, 1.5, 2],
            "message": message,
        },
    )


@router.post("/settings")
async def update_settings(
    request: Request,
    serial_port: str | None = Form(default=None),
    baud_rate: int = Form(default=9600),
    parity: str = Form(default="N"),
    stop_bits: float = Form(default=1.0),
    audio_device: str | None = Form(default=None),
    session=Depends(get_session),
    serial_service: SerialService = Depends(get_serial_service),
    audio_streamer: SoundDeviceStreamer = Depends(get_audio_streamer),
) -> RedirectResponse:
    repo = SettingsRepository(session)
    updated = repo.update(
        {
            "serial_port": serial_port or None,
            "baud_rate": baud_rate,
            "parity": parity,
            "stop_bits": float(stop_bits),
            "audio_device": audio_device or None,
        }
    )

    config = SerialConfiguration(
        port=updated.serial_port,
        baud_rate=updated.baud_rate,
        parity=updated.parity,
        stop_bits=updated.stop_bits,
    )

    await serial_service.apply_configuration(config)
    await audio_streamer.set_device(updated.audio_device)

    message = quote_plus("設定を更新しました。")
    base_url = str(request.url_for("settings_page"))
    redirect_url = f"{base_url}?msg={message}"
    return RedirectResponse(redirect_url, status_code=303)


@router.post("/transmit")
async def transmit(
    request: Request,
    payload: str = Form(...),
    serial_service: SerialService = Depends(get_serial_service),
) -> RedirectResponse:
    try:
        await serial_service.send_command(payload)
        message = "送信しました。"
    except Exception as exc:  # pylint: disable=broad-except
        message = f"送信に失敗しました: {exc}"
    encoded_message = quote_plus(message)
    base_url = str(request.url_for("index"))
    redirect_url = f"{base_url}?msg={encoded_message}"
    return RedirectResponse(redirect_url, status_code=303)


@router.websocket("/audio/ws", name="audio_ws")
async def audio_ws(
    websocket: WebSocket,
    audio_streamer: SoundDeviceStreamer = Depends(get_audio_streamer),
) -> None:
    await websocket.accept()
    subscriber_id = audio_streamer.register()
    queue = audio_streamer.queue_for(subscriber_id)
    try:
        while True:
            data = await queue.get()
            await websocket.send_bytes(data)
    except WebSocketDisconnect:
        logger.debug("WebSocket disconnected: %s", websocket.client)
    except Exception as exc:  # pylint: disable=broad-except
        logger.error("Audio streaming error: %s", exc)
        await websocket.close(code=1011, reason=str(exc))
    finally:
        audio_streamer.unregister(subscriber_id)
