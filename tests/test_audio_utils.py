from app.audio.playback import PlaybackService


def _create_service() -> PlaybackService:
    service = PlaybackService(sample_rate=48000, block_size=1024)
    return service


def test_playback_callback_zero_fill() -> None:
    service = _create_service()
    out = bytearray(8)  # 4 frames * 2 bytes
    service._callback(out, 4, None, None)  # type: ignore[arg-type]
    assert bytes(out) == b"\x00" * 8


def test_playback_callback_with_buffered_data() -> None:
    service = _create_service()
    service._buffer.extend(b"\x01\x02" * 4)
    out = bytearray(8)
    service._callback(out, 4, None, None)  # type: ignore[arg-type]
    assert bytes(out) == b"\x01\x02" * 4
