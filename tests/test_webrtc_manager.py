import asyncio

import pytest
from aiortc import MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from av import AudioFrame
from fractions import Fraction

from app.webrtc.manager import WebRTCManager


class DummyStreamer:
    sample_rate = 48000

    def __init__(self) -> None:
        self.subscribers = {}
        self.counter = 0

    def register(self) -> int:
        idx = self.counter
        self.counter += 1
        queue = asyncio.Queue()
        queue.put_nowait(b"\x00" * 960 * 2)
        self.subscribers[idx] = queue
        return idx

    def unregister(self, subscriber_id: int) -> None:
        self.subscribers.pop(subscriber_id, None)

    def queue_for(self, subscriber_id: int):
        return self.subscribers[subscriber_id]


class DummyPlaybackService:
    def __init__(self) -> None:
        self.sender_id = None
        self.frames = 0

    def available_devices(self):
        return []

    async def handle_frame(self, frame: AudioFrame) -> None:
        self.frames += 1

    def acquire(self, sender_id: str) -> bool:
        if self.sender_id and self.sender_id != sender_id:
            return False
        self.sender_id = sender_id
        return True

    def release(self, sender_id: str) -> None:
        if self.sender_id == sender_id:
            self.sender_id = None


class SilentAudioTrack(MediaStreamTrack):
    kind = "audio"

    def __init__(self) -> None:
        super().__init__()
        self._pts = 0
        self._time_base = Fraction(1, 48000)

    async def recv(self) -> AudioFrame:
        samples = 960
        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.planes[0].update(b"\x00" * samples * 2)
        frame.sample_rate = 48000
        frame.pts = self._pts
        frame.time_base = self._time_base
        self._pts += samples
        return frame


@pytest.mark.asyncio
async def test_webrtc_manager_process_offer() -> None:
    streamer = DummyStreamer()
    playback = DummyPlaybackService()
    manager = WebRTCManager(streamer, playback)

    pc = RTCPeerConnection()
    pc.addTransceiver("audio", direction="recvonly")
    pc.addTrack(SilentAudioTrack())

    offer = await pc.createOffer()
    await pc.setLocalDescription(offer)

    answer_dict = await manager.process_offer(pc.localDescription)
    assert answer_dict["type"] == "answer"

    answer = RTCSessionDescription(sdp=answer_dict["sdp"], type=answer_dict["type"])
    await pc.setRemoteDescription(answer)
    await pc.close()
    await asyncio.sleep(0)
    await manager.shutdown()
