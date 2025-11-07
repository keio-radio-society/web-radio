import asyncio
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, create_engine

from app import config as app_config
from app import db as app_db
from app import dependencies as app_dependencies
from app import main as app_main
from app.repositories import SettingsRepository
from app.web import routes as web_routes


class DummySerialService:
    def __init__(self) -> None:
        self.commands: List[str] = []
        self.config_history: List[Dict[str, Any]] = []

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def send_command(self, payload: str) -> None:
        self.commands.append(payload)

    async def apply_configuration(self, config) -> None:
        self.config_history.append(config.model_dump())

    @staticmethod
    def available_ports() -> List[Dict[str, str]]:
        return [{"device": "/dev/ttyUSB0", "description": "Dummy USB"}]


class DummyAudioStreamer:
    def __init__(self) -> None:
        self.device: Optional[str] = None
        self.started = False
        self.subscribers: Dict[int, asyncio.Queue[bytes]] = {}
        self.counter = 0
        self._sample_rate = 48000
        self._block_size = 960

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.started = False

    async def set_device(self, device: Optional[str]) -> None:
        self.device = device or "default"

    def register(self) -> int:
        queue: asyncio.Queue[bytes] = asyncio.Queue()
        queue.put_nowait(b"\x00\x01" * 10)
        subscriber_id = self.counter
        self.counter += 1
        self.subscribers[subscriber_id] = queue
        return subscriber_id

    def unregister(self, subscriber_id: int) -> None:
        self.subscribers.pop(subscriber_id, None)

    def queue_for(self, subscriber_id: int) -> asyncio.Queue[bytes]:
        return self.subscribers[subscriber_id]

    def available_devices(self) -> List[Dict[str, str]]:
        return [{"id": "0", "description": "Dummy Device"}]


class DummyPlaybackService:
    def __init__(self) -> None:
        self.device: Optional[str] = None
        self.queue: List[bytes] = []
        self.active_sender: Optional[str] = None

    async def start(self) -> None:
        return

    async def stop(self) -> None:
        return

    async def set_device(self, device: Optional[str]) -> None:
        self.device = device or "default"

    def available_devices(self) -> List[Dict[str, str]]:
        return [{"id": "1", "description": "Dummy Speaker"}]

    def can_acquire(self) -> bool:
        return self.active_sender is None

    def acquire(self, sender_id: str) -> bool:
        if self.active_sender and self.active_sender != sender_id:
            return False
        self.active_sender = sender_id
        return True

    def release(self, sender_id: str) -> None:
        if self.active_sender == sender_id:
            self.active_sender = None

    async def enqueue(self, data: bytes) -> None:
        self.queue.append(data)


class DummyWebRTCManager:
    def __init__(self, *_args, **_kwargs) -> None:
        self.calls: List[Dict[str, Any]] = []

    async def process_offer(self, offer, session_id=None):
        self.calls.append({"offer": offer, "session_id": session_id})
        return {"sdp": "answer-sdp", "type": "answer", "session_id": "session-1"}

    async def shutdown(self) -> None:
        return


@dataclass
class TestContext:
    client: TestClient
    serial_service: DummySerialService
    audio_streamer: DummyAudioStreamer
    playback_service: DummyPlaybackService
    webrtc_manager: DummyWebRTCManager


TestContext.__test__ = False


@pytest.fixture()
def test_context(tmp_path, monkeypatch) -> TestContext:
    db_path = tmp_path / "app.db"
    test_engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False},
    )

    monkeypatch.setattr(app_db, "engine", test_engine, raising=False)
    monkeypatch.setattr(app_config.settings, "database_path", db_path)
    monkeypatch.setattr(app_dependencies, "engine", test_engine, raising=False)

    monkeypatch.setattr(app_main, "SerialService", DummySerialService)
    monkeypatch.setattr(app_main, "SoundDeviceStreamer", DummyAudioStreamer)
    monkeypatch.setattr(app_main, "PlaybackService", DummyPlaybackService)
    monkeypatch.setattr(app_main, "WebRTCManager", DummyWebRTCManager)
    monkeypatch.setattr(web_routes, "SerialService", DummySerialService)
    monkeypatch.setattr(web_routes, "SoundDeviceStreamer", DummyAudioStreamer)
    monkeypatch.setattr(web_routes, "PlaybackService", DummyPlaybackService)

    with TestClient(app_main.app) as client:
        serial_service = client.app.state.serial_service
        audio_streamer = client.app.state.audio_streamer
        playback_service = client.app.state.playback_service
        webrtc_manager = client.app.state.webrtc_manager
        yield TestContext(
            client=client,
            serial_service=serial_service,
            audio_streamer=audio_streamer,
            playback_service=playback_service,
            webrtc_manager=webrtc_manager,
        )


def test_get_settings_page(test_context: TestContext) -> None:
    response = test_context.client.get("/settings")
    assert response.status_code == 200
    assert "設定" in response.text
    assert "/dev/ttyUSB0" in response.text


def test_update_settings_persists_and_notifies_services(test_context: TestContext) -> None:
    response = test_context.client.post(
        "/settings",
        data={
            "serial_port": "/dev/ttyUSB0",
            "baud_rate": "19200",
            "parity": "E",
            "stop_bits": "2",
            "audio_device": "dummy",
            "playback_device": "1",
        },
        allow_redirects=False,
    )

    assert response.status_code == 303
    assert test_context.serial_service.config_history[-1] == {
        "port": "/dev/ttyUSB0",
        "baud_rate": 19200,
        "parity": "E",
        "stop_bits": 2.0,
    }
    assert test_context.audio_streamer.device == "dummy"
    assert test_context.playback_service.device == "1"

    with Session(app_db.engine) as session:
        repo = SettingsRepository(session)
        stored = repo.get()
        assert stored.serial_port == "/dev/ttyUSB0"
        assert stored.baud_rate == 19200
        assert stored.parity == "E"
        assert stored.stop_bits == 2.0
        assert stored.audio_device == "dummy"
        assert stored.audio_playback_device == "1"


def test_transmit_enqueues_command(test_context: TestContext) -> None:
    response = test_context.client.post(
        "/transmit",
        data={"payload": "TEST"},
        allow_redirects=False,
    )

    assert response.status_code == 303
    assert test_context.serial_service.commands == ["TEST"]


def test_webrtc_session_endpoint_calls_manager(test_context: TestContext) -> None:
    response = test_context.client.post(
        "/webrtc/session",
        json={"sdp": "offer-sdp", "type": "offer", "session_id": None},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["sdp"] == "answer-sdp"
    assert data["session_id"] == "session-1"
    assert test_context.webrtc_manager.calls[0]["offer"].sdp == "offer-sdp"
