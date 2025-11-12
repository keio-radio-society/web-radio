from __future__ import annotations

import asyncio
from fractions import Fraction
from typing import Optional

import av
import numpy as np
from aiortc import AudioStreamTrack

from app.audio.streamer import SoundDeviceStreamer


class StreamerAudioTrack(AudioStreamTrack):
    """Wrap SoundDeviceStreamer queue as an aiortc AudioStreamTrack."""

    def __init__(self, streamer: SoundDeviceStreamer) -> None:
        super().__init__()
        self._streamer = streamer
        self._subscriber_id = streamer.register()
        self._queue = streamer.queue_for(self._subscriber_id)
        self._pts = 0
        self._time_base = Fraction(1, int(streamer.sample_rate))
        self._closed = False

    async def recv(self) -> av.AudioFrame:
        if self._closed:
            raise asyncio.CancelledError

        data = await self._queue.get()
        samples = np.frombuffer(data, dtype=np.int16)
        frame = av.AudioFrame.from_ndarray(
            samples.reshape(1, -1), format="s16", layout="mono"
        )
        frame.sample_rate = int(self._streamer.sample_rate)
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += samples.shape[0]
        return frame

    async def stop(self) -> None:
        if not self._closed:
            self._streamer.unregister(self._subscriber_id)
            self._closed = True
        super().stop()
