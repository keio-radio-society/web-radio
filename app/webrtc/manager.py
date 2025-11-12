from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Dict, Optional
from uuid import uuid4

from aiortc import RTCPeerConnection, RTCSessionDescription

from app.audio.playback import PlaybackService
from app.audio.streamer import SoundDeviceStreamer
from app.webrtc.tracks import StreamerAudioTrack

logger = logging.getLogger(__name__)


class WebRTCSession:
    def __init__(
        self,
        session_id: str,
        pc: RTCPeerConnection,
        track: StreamerAudioTrack,
    ) -> None:
        self.id = session_id
        self.pc = pc
        self.track = track
        self.playback_task: Optional[asyncio.Task] = None


class WebRTCManager:
    def __init__(
        self,
        streamer: SoundDeviceStreamer,
        playback_service: PlaybackService,
    ) -> None:
        self._streamer = streamer
        self._playback = playback_service
        self._sessions: Dict[str, WebRTCSession] = {}

    async def process_offer(
        self,
        offer: RTCSessionDescription,
        session_id: Optional[str] = None,
    ) -> Dict:
        session = await self._ensure_session(session_id)
        pc = session.pc

        await pc.setRemoteDescription(offer)
        answer = await pc.createAnswer()
        await pc.setLocalDescription(answer)

        return {
            "sdp": pc.localDescription.sdp,
            "type": pc.localDescription.type,
            "session_id": session.id,
        }

    async def shutdown(self) -> None:
        for session_id in list(self._sessions.keys()):
            await self._close_session(session_id)

    async def _ensure_session(self, session_id: Optional[str]) -> WebRTCSession:
        if session_id and session_id in self._sessions:
            return self._sessions[session_id]

        pc = RTCPeerConnection()
        pc.addTransceiver("audio", direction="sendrecv")
        track = StreamerAudioTrack(self._streamer)
        pc.addTrack(track)

        new_session = WebRTCSession(str(uuid4()), pc, track)
        self._sessions[new_session.id] = new_session

        @pc.on("track")
        async def on_track(remote_track):
            if remote_track.kind != "audio":
                return
            if not self._playback.acquire(new_session.id):
                logger.warning("Playback busy, rejecting new sender")
                await remote_track.stop()
                return
            new_session.playback_task = asyncio.create_task(
                self._consume_remote_audio(new_session, remote_track),
                name=f"webrtc-playback-{new_session.id}",
            )

        @pc.on("connectionstatechange")
        async def on_connectionstatechange():
            if pc.connectionState in ("failed", "closed"):
                await self._close_session(new_session.id)

        return new_session

    async def _consume_remote_audio(
        self,
        session: WebRTCSession,
        remote_track,
    ) -> None:
        try:
            while True:
                frame = await remote_track.recv()
                await self._playback.handle_frame(frame)
        except Exception as exc:  # pylint: disable=broad-except
            logger.warning("Playback consume error: %s", exc)
        finally:
            self._playback.release(session.id)

    async def _close_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if not session:
            return

        if session.playback_task:
            session.playback_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await session.playback_task
        await session.track.stop()
        await session.pc.close()
        self._playback.release(session_id)
