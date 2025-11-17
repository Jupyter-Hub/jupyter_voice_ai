import sounddevice as sd
import os
import io
import wave

from pydub import AudioSegment
from pydub.playback import play

def pcm16_to_wav(pcm_data, sample_rate=24000, channels=1):
    wav_buffer = io.BytesIO()
    with wave.open(wav_buffer, "wb") as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # PCM16 has 2 bytes per sample
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_data)

    return wav_buffer.getvalue()


def select_input_device():
    """
    Selects the input device for recording audio.
    """
    devices = sd.query_devices()
    index = int(os.getenv("MICROPHONE_DEVICE_ID"))
    i = 0
    for device in devices:
        if int(device['max_input_channels']) > 0:
            i += 1
        if i == index:
            device_id = device['index']
            return device_id

    print("No suitable input device found.")
    return 0


def select_output_device():
    """
    Selects the input device for recording audio.
    """
    devices = sd.query_devices()
    index = int(os.getenv("SPEAKER_DEVICE_ID"))
    i = 0
    for device in devices:
        if int(device['max_output_channels']) > 0:
            i += 1
        if i == index:
            device_id = device['index']
            return device_id
            break

    print("No suitable output device found.")
    return 0

