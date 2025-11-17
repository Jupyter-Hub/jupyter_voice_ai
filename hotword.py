import numpy as np
import openwakeword

openwakeword.utils.download_models()
owwModel = openwakeword.Model(wakeword_models=["./hey_jupiter.onnx"], inference_framework='onnx')

CHUNK = 1280  # Default chunk size for processing

n_models = len(owwModel.models.keys())

def listen_for_hotword(mic_stream):
    # Read CHUNK frames. This returns a tuple (data, overflow_flag)
    mic_stream.start()
    data, overflow = mic_stream.read(CHUNK)
    # Convert the raw data (memoryview) to a NumPy array.
    audio_data = np.frombuffer(data, dtype=np.int16)

    prediction = owwModel.predict(audio_data)
    print(prediction)
    for mdl in owwModel.prediction_buffer.keys():
        scores = list(owwModel.prediction_buffer[mdl])
        if scores[-1] > 0.2:
            return True
    return False
