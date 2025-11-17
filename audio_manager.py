import asyncio
import audioop
import functools
import queue
import threading
import time
from collections import deque
from typing import Deque
import openwakeword

import numpy as np
import sounddevice as sd
import webrtcvad
from dotenv import load_dotenv
from state import Singleton

# Load environment variables (e.g., for wakeword model paths)
load_dotenv()

# Audio settings
RATE = 48_000
CHUNK_SAMPLES = 1280
CHUNK_BYTES = CHUNK_SAMPLES * 2

# VAD settings
VAD_FRAME_MS = 30
VAD_FRAME_SAMPLES = RATE * VAD_FRAME_MS // 1000
VAD_FRAME_BYTES = VAD_FRAME_SAMPLES * 2

# Recording timeouts and buffers
BUFFER_SECONDS = 1.0
SPEECH_START_TIMEOUT = 5.0         # grace-time to begin speaking
SILENCE_TIMEOUT_AFTER_SPEECH = 1.0 # trailing-silence to stop
MAX_SILENCE_FRAMES = int(SILENCE_TIMEOUT_AFTER_SPEECH * 1000 / VAD_FRAME_MS)

# False-positive suppression: require N consecutive speech frames to start
SPEECH_START_MIN_FRAMES = 3

# Minimal speech threshold
MIN_SPEECH_DURATION = 0.3          # seconds of speech to count as valid
MIN_SPEECH_BYTES    = int(MIN_SPEECH_DURATION * RATE * 2)

# Wakeword detection threshold
WAKE_THRESHOLD = 0.2


@functools.lru_cache
def _load_oww_model():
    openwakeword.utils.download_models()
    return openwakeword.Model(
        wakeword_models=["./hey_jupiter.onnx"],
        inference_framework="onnx",
    )


class AudioManager(metaclass=Singleton):
    """
    Manages audio I/O: wakeword detection, recording, and playback.
    """
    def __init__(self):
        # Playback and wakeword events
        self.play_q: "queue.Queue[bytes]" = queue.Queue()
        self.wake_event = asyncio.Event()
        self.stop_playback_event = threading.Event()

        # Recording state
        self.recording_bytes = bytearray()
        self.record_done = asyncio.Event()

        # VAD internals
        self._vad = webrtcvad.Vad(1)
        self._vad_buffer = bytearray()
        self._vad_ring: Deque[bool] = deque(
            maxlen=int(BUFFER_SECONDS * 1000 / VAD_FRAME_MS)
        )
        # Suppress false positives by requiring consecutive speech frames
        self._start_ring: Deque[bool] = deque(maxlen=SPEECH_START_MIN_FRAMES)

        self._is_recording = False
        self._speech_started = False
        self._recording_started_at = 0.0

        # Flag for no/insufficient speech
        self.no_speech = False

        # Start audio streaming thread
        self._stream_thread = threading.Thread(target=self._run_stream, daemon=True)
        self._stream_thread.start()

    def play(self, pcm24k: bytes):
        """Enqueue resampled 16k audio for playback."""
        pcm16k, _ = audioop.ratecv(pcm24k, 2, 1, 24_000, RATE, None)
        for i in range(0, len(pcm16k), CHUNK_BYTES):
            self.play_q.put_nowait(pcm16k[i:i + CHUNK_BYTES])

    def start_recording(self):
        """Begin VAD-based recording session."""
        self.recording_bytes.clear()
        self.record_done.clear()
        self._is_recording = True
        self._speech_started = False
        self._recording_started_at = time.monotonic()
        self._vad_ring.clear()
        self._start_ring.clear()
        self.no_speech = False

    def _run_stream(self):
        stream = sd.RawStream(
            samplerate=RATE,
            channels=1,
            dtype="int16",
            blocksize=CHUNK_SAMPLES,
            callback=self._callback,
            latency="low",
        )
        stream.start()
        asyncio.run(self._keep_alive())

    async def _keep_alive(self):
        while True:
            await asyncio.sleep(60)

    def _callback(self, in_data, out_data, frames, time_info, status):
        pcm_in = memoryview(in_data)
        # Wakeword detection
        mdl = _load_oww_model()
        mdl.predict(np.frombuffer(pcm_in, dtype=np.int16))
        if any(buf and buf[-1] > WAKE_THRESHOLD for buf in mdl.prediction_buffer.values()):
            self.wake_event.set()
            self.stop_playback_event.set()

        # VAD processing
        self._vad_buffer.extend(pcm_in)
        while len(self._vad_buffer) >= VAD_FRAME_BYTES:
            frame = self._vad_buffer[:VAD_FRAME_BYTES]
            del self._vad_buffer[:VAD_FRAME_BYTES]
            is_speech = self._vad.is_speech(frame, RATE)

            if self._is_recording:
                # Before speech start: buffer recent decisions
                if not self._speech_started:
                    self._start_ring.append(is_speech)
                    # require several consecutive true detections
                    if len(self._start_ring) == self._start_ring.maxlen and all(self._start_ring):
                        self._speech_started = True
                        self.recording_bytes.clear()
                        self._vad_ring.clear()
                    # timeout waiting for speech
                    elif time.monotonic() - self._recording_started_at > SPEECH_START_TIMEOUT:
                        self.no_speech = True
                        self._is_recording = False
                        self.record_done.set()
                        continue

                # Once started, collect and detect end
                if self._speech_started:
                    self.recording_bytes.extend(frame)
                    self._vad_ring.append(is_speech)
                    if len(self._vad_ring) > MAX_SILENCE_FRAMES:
                        self._vad_ring.popleft()
                    if len(self._vad_ring) == MAX_SILENCE_FRAMES and not any(self._vad_ring):
                        if len(self.recording_bytes) < MIN_SPEECH_BYTES:
                            self.no_speech = True
                        self._is_recording = False
                        self.record_done.set()

        # Playback handling
        if self.stop_playback_event.is_set():
            while not self.play_q.empty():
                self.play_q.get_nowait()
            out_data[:] = b"\x00" * CHUNK_BYTES
            return

        try:
            chunk = self.play_q.get_nowait()
        except queue.Empty:
            out_data[:] = b"\x00" * CHUNK_BYTES
        else:
            if len(chunk) < CHUNK_BYTES:
                chunk += b"\x00" * (CHUNK_BYTES - len(chunk))
            out_data[:CHUNK_BYTES] = chunk


async def record_voice_input(timeout: int = 20) -> bytes | None:
    """
    Record speech until silence or timeout; return None if insufficient speech.
    """
    audio = AudioManager()
    audio.start_recording()
    try:
        await asyncio.wait_for(audio.record_done.wait(), timeout=timeout)
    except asyncio.TimeoutError:
        audio.no_speech = True

    if audio.no_speech or len(audio.recording_bytes) < MIN_SPEECH_BYTES:
        return None
    return bytes(audio.recording_bytes)
