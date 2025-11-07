import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

try:
    import sounddevice as sd  # type: ignore
except (ImportError, OSError) as exc:  # pragma: no cover - handled at runtime
    sd = None  # type: ignore[assignment]
    _SOUNDDEVICE_IMPORT_ERROR = exc
else:
    _SOUNDDEVICE_IMPORT_ERROR = None

logger = logging.getLogger(__name__)


class AudioStreamError(RuntimeError):
    """Raised when audio streaming cannot be prepared or executed."""


@dataclass
class AudioDeviceInfo:
    id: int
    name: str


class SoundDeviceStreamer:
    """Capture microphone audio via sounddevice and distribute to subscribers."""

    def __init__(
        self,
        sample_rate: int = 48000,
        block_size: int = 2048,
        channels: int = 1,
        dtype: str = "int16",
        latency: float = 0.1,
    ) -> None:
        self._sample_rate = sample_rate
        self._block_size = block_size
        self._channels = channels
        self._dtype = dtype
        self._latency = latency

        self._device: Optional[int] = None
        self._stream: Optional[Any] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._lock = asyncio.Lock()
        self._subscribers: Dict[int, asyncio.Queue[bytes]] = {}
        self._subscriber_id = 0

    async def start(self) -> None:
        async with self._lock:
            if self._stream is not None:
                return

            self._loop = asyncio.get_running_loop()

            try:
                backend = self._require_backend()
                self._stream = backend.RawInputStream(
                    device=self._device,
                    samplerate=self._sample_rate,
                    blocksize=self._block_size,
                    channels=self._channels,
                    dtype=self._dtype,
                    latency=self._latency,
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:  # pylint: disable=broad-except
                logger.exception("Failed to start audio stream: %s", exc)
                raise AudioStreamError(f"音声入力ストリームを開始できません: {exc}") from exc

    async def stop(self) -> None:
        async with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None

    async def set_device(self, device: Optional[str | int]) -> None:
        """Update the capture device. Passing None uses default."""

        parsed = self._parse_device(device)
        async with self._lock:
            if parsed == self._device:
                return
            self._device = parsed

            if self._stream is not None:
                await self._restart_locked()

    def register(self) -> int:
        queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=1000)
        subscriber_id = self._subscriber_id
        self._subscriber_id += 1
        self._subscribers[subscriber_id] = queue
        return subscriber_id

    def unregister(self, subscriber_id: int) -> None:
        self._subscribers.pop(subscriber_id, None)

    def queue_for(self, subscriber_id: int) -> asyncio.Queue[bytes]:
        queue = self._subscribers.get(subscriber_id)
        if queue is None:
            raise KeyError(f"Subscriber {subscriber_id} not registered")
        return queue

    def available_devices(self) -> List[Dict[str, str]]:
        try:
            backend = self._require_backend()
            devices = backend.query_devices()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to query audio devices: %s", exc)
            return []

        result: List[Dict[str, str]] = []
        for index, device in enumerate(devices):
            if int(device.get("max_input_channels", 0)) <= 0:
                continue
            name = device.get("name", f"Device {index}")
            hostapi = backend.query_hostapis()[device["hostapi"]]["name"]
            result.append(
                {
                    "id": str(index),
                    "description": f"{name} ({hostapi})",
                }
            )
        return result

    def _parse_device(self, device: Optional[str | int]) -> Optional[int]:
        if device is None or device == "":
            return None
        try:
            return int(device)
        except (TypeError, ValueError):
            # Attempt to find device by name
            try:
                backend = self._require_backend()
                devices = backend.query_devices()
            except Exception as exc:  # pylint: disable=broad-except
                raise AudioStreamError("オーディオデバイス情報を取得できませんでした。") from exc

            for index, info in enumerate(devices):
                if info.get("name") == device:
                    return index
            raise AudioStreamError(f"指定されたデバイスが見つかりません: {device}")

    async def _restart_locked(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._stream = None
        await self.start()

    def _callback(self, indata, frames, time_info, status) -> None:  # type: ignore[override]
        if status:
            logger.warning("Audio callback status: %s", status)

        if self._loop is None:
            return

        data = bytes(indata)
        self._loop.call_soon_threadsafe(self._broadcast, data)

    def _broadcast(self, data: bytes) -> None:
        for subscriber_id, queue in list(self._subscribers.items()):
            try:
                queue.put_nowait(data)
            except asyncio.QueueFull:
                logger.debug("Dropping audio frame for subscriber %s (queue full)", subscriber_id)

    def _require_backend(self):
        if sd is None:
            raise AudioStreamError(
                "PortAudio ライブラリが見つかりません。'sounddevice' を利用するには libportaudio の導入が必要です。"
            ) from _SOUNDDEVICE_IMPORT_ERROR
        return sd
