"""Lazy audio-device access. Importing this module never starts recording."""
import threading
import numpy as np


def to_mono_16k(samples, sample_rate, channels=1):
    audio = np.asarray(samples, dtype=np.float32).reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000 and len(audio):
        count = max(1, round(len(audio)*16000/sample_rate))
        audio = np.interp(np.arange(count)*sample_rate/16000, np.arange(len(audio)), audio).astype(np.float32)
    return np.clip(audio, -1, 1)


class AudioCapture:
    def __init__(self, source, device=None):
        self.source, self.device = source, device

    def run(self, stop: threading.Event, sink, notice):
        if self.source == 'microphone':
            import sounddevice as sd
            details = sd.query_devices(self.device, 'input')
            rate = int(details['default_samplerate'])
            frames = max(1, round(rate*.2))
            with sd.RawInputStream(device=self.device, channels=1, samplerate=rate,
                                   blocksize=frames, dtype='float32') as stream:
                while not stop.is_set():
                    raw, overflow = stream.read(frames)
                    if overflow:
                        notice('input_overflow', 'Microphone device reported lost samples; review the audio around this point.')
                    sink('microphone', to_mono_16k(np.frombuffer(raw, dtype=np.float32), rate))
        elif self.source == 'system':
            import pyaudiowpatch as pa
            with pa.PyAudio() as audio:
                device = audio.get_default_wasapi_loopback()
                rate, channels = int(device['defaultSampleRate']), int(device['maxInputChannels'])
                frames = max(1, round(rate*.2))
                with audio.open(format=pa.paFloat32, channels=channels, rate=rate,
                                input=True, input_device_index=device['index'], frames_per_buffer=frames) as stream:
                    while not stop.is_set():
                        raw = stream.read(frames, exception_on_overflow=True)
                        sink('system', to_mono_16k(np.frombuffer(raw, dtype=np.float32), rate, channels))
        else:
            raise ValueError('Unsupported audio source')


def make_captures(settings):
    names = ['microphone', 'system'] if settings.source == 'both' else [settings.source]
    return [AudioCapture(name, settings.microphone_device) for name in names]
