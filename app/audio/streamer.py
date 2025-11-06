import asyncio
import logging
import re
import subprocess
from typing import AsyncIterator, Dict, List, Optional

logger = logging.getLogger(__name__)


class AudioStreamer:
    """FFmpeg-based audio capture helper."""

    def __init__(self, ffmpeg_path: str = "ffmpeg") -> None:
        self._ffmpeg_path = ffmpeg_path
        self._device: str = "default"
        self._lock = asyncio.Lock()

    async def set_device(self, device: Optional[str]) -> None:
        async with self._lock:
            self._device = device or "default"

    async def stream(self) -> AsyncIterator[bytes]:
        async with self._lock:
            device = self._device

        process = await asyncio.create_subprocess_exec(
            self._ffmpeg_path,
            "-hide_banner",
            "-loglevel",
            "error",
            "-f",
            "alsa",
            "-i",
            device,
            "-ac",
            "1",
            "-ar",
            "48000",
            "-c:a",
            "libopus",
            "-b:a",
            "64k",
            "-frame_duration",
            "60",
            "-application",
            "audio",
            "-f",
            "ogg",
            "-",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        stderr_task = asyncio.create_task(self._drain_stderr(process))

        try:
            assert process.stdout is not None
            while True:
                chunk = await process.stdout.read(4096)
                if not chunk:
                    break
                yield chunk
        finally:
            if process.returncode is None:
                process.kill()
            await process.wait()
            stderr_task.cancel()

    async def _drain_stderr(self, process: asyncio.subprocess.Process) -> None:
        if process.stderr is None:
            return
        try:
            while True:
                line = await process.stderr.readline()
                if not line:
                    break
                logger.debug("ffmpeg: %s", line.decode(errors="ignore").strip())
        except asyncio.CancelledError:
            pass

    @staticmethod
    def available_devices() -> List[Dict[str, str]]:
        devices: List[Dict[str, str]] = [
            {"id": "pulse", "description": "PulseAudio"},
        ]

        try:
            result = subprocess.run(
                ["arecord", "-l"],
                capture_output=True,
                text=True,
                check=False,
            )
        except FileNotFoundError:
            return devices

        card_pattern = re.compile(
            r"card\s+(?P<card>\d+):\s+(?P<card_name>[^\[]+)\[(?P<card_desc>[^\]]+)\],\s+device\s+(?P<device>\d+):\s+(?P<device_name>[^\[]+)\[(?P<device_desc>[^\]]+)\]"
        )

        for line in result.stdout.splitlines():
            match = card_pattern.search(line)
            if not match:
                continue
            card = match.group("card")
            device = match.group("device")
            identifier = f"hw:{card},{device}"
            description = f"{match.group('card_desc').strip()} - {match.group('device_desc').strip()}"
            devices.append({"id": identifier, "description": description})

        seen = set()
        unique_devices = []
        for device in devices:
            if device["id"] in seen:
                continue
            seen.add(device["id"])
            unique_devices.append(device)
        return unique_devices

    async def stop(self) -> None:
        # This implementation spawns a new FFmpeg process per stream, so nothing to stop globally.
        return
