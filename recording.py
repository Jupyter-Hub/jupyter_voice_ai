import asyncio
from audio_manager import AudioManager, MIN_SPEECH_BYTES

async def record_voice_input(timeout: int = 20) -> bytes | None:
    audio = AudioManager()
    audio.start_recording()
    try:
        await asyncio.wait_for(audio.record_done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        # also treat timeout (no record_done) as no speech
        audio.no_speech = True

    # if we never really heard anything, return None
    if audio.no_speech or len(audio.recording_bytes) < MIN_SPEECH_BYTES:
        return None

    return bytes(audio.recording_bytes)
