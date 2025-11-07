import asyncio
import logging
from typing import Any, Dict, List, Optional

import av
import numpy as np

try:
    import sounddevice as sd  # type: ignore
except (ImportError, OSError) as exc:  # pragma: no cover
    sd = None  # type: ignore[assignment]
    _SOUNDDEVICE_IMPORT_ERROR = exc
else:
    _SOUNDDEVICE_IMPORT_ERROR = None

logger = logging.getLogger(__name__)


class PlaybackError(RuntimeError):
    """Raised when playback cannot be configured."""


class PlaybackService:
    """Manage exclusive audio playback from browser uploads."""

    def __init__(
        self,
        sample_rate: int = 48000,
        block_size: int = 2048,
        channels: int = 1,
        dtype: str = "int16",
        latency: float = 0.15,
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
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(maxsize=4000)
        self._buffer = bytearray()
        self._active_sender: Optional[str] = None

    async def start(self) -> None:
        async with self._lock:
            if self._stream is not None:
                return

            self._loop = asyncio.get_running_loop()

            try:
                backend = self._require_backend()
                self._stream = backend.RawOutputStream(
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
                logger.exception("Failed to start playback stream: %s", exc)
                raise PlaybackError(f"音声出力を初期化できません: {exc}") from exc

    async def stop(self) -> None:
        async with self._lock:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
                self._stream = None
        await self._clear_queue()

    async def set_device(self, device: Optional[str | int]) -> None:
        parsed = self._parse_device(device)

        async with self._lock:
            if parsed == self._device:
                return
            self._device = parsed
            if self._stream is not None:
                await self._restart_locked()

    def can_acquire(self) -> bool:
        return self._active_sender is None

    def acquire(self, sender_id: str) -> bool:
        if self._active_sender and self._active_sender != sender_id:
            return False
        self._active_sender = sender_id
        return True

    def release(self, sender_id: str) -> None:
        if self._active_sender == sender_id:
            self._active_sender = None

    async def enqueue(self, data: bytes) -> None:
        try:
            await self._queue.put(data)
        except asyncio.QueueFull:
            logger.warning("Playback queue overflow, dropping audio chunk")

    async def handle_frame(self, frame: av.AudioFrame) -> None:
        pcm = frame.to_ndarray(format="s16")
        if pcm.ndim == 2 and pcm.shape[0] > 1:
            # downmix to mono
            pcm = np.mean(pcm, axis=0, dtype=np.int16, keepdims=True)
        interleaved = pcm.reshape(-1).astype(np.int16)
        await self.enqueue(interleaved.tobytes())

    def available_devices(self) -> List[Dict[str, str]]:
        try:
            backend = self._require_backend()
            devices = backend.query_devices()
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Failed to query playback devices: %s", exc)
            return []

        result: List[Dict[str, str]] = []
        for index, device in enumerate(devices):
            if int(device.get("max_output_channels", 0)) <= 0:
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

    async def _restart_locked(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
        self._stream = None
        await self.start()

    async def _clear_queue(self) -> None:
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:  # pragma: no cover
                break
        self._buffer.clear()

    def _callback(self, outdata, frames, time_info, status) -> None:  # type: ignore[override]
        if status:
            logger.warning("Playback callback status: %s", status)

        bytes_needed = frames * self._channels * 2
        while len(self._buffer) < bytes_needed and not self._queue.empty():
            chunk = self._queue.get_nowait()
            self._buffer.extend(chunk)

        target = memoryview(outdata).cast("b")
        if len(self._buffer) < bytes_needed:
            target[:] = b"\x00" * len(target)
        else:
            target[:] = self._buffer[: len(target)]
            del self._buffer[:bytes_needed]

    def _parse_device(self, device: Optional[str | int]) -> Optional[int]:
        if device in (None, ""):
            return None
        try:
            return int(device)
        except (TypeError, ValueError):
            try:
                backend = self._require_backend()
                devices = backend.query_devices()
            except Exception as exc:  # pylint: disable=broad-except
                raise PlaybackError("出力デバイス情報を取得できませんでした。") from exc
            for index, info in enumerate(devices):
                if info.get("name") == device:
                    return index
            raise PlaybackError(f"指定された出力デバイスが見つかりません: {device}")

    def _require_backend(self):
        if sd is None:
            raise PlaybackError(
                "PortAudio ライブラリが見つかりません。'sounddevice' を利用するには libportaudio の導入が必要です。"
            ) from _SOUNDDEVICE_IMPORT_ERROR
        return sd
