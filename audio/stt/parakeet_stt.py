"""Local Parakeet adapter for Clicky's regular talk/dictation path."""
import asyncio
import os
import threading
import numpy as np
from audio.stt.base_stt import BaseSTT
from classroom.capture import to_mono_16k
from classroom.engines import LocalTranscriber
from classroom.settings import Settings
from classroom.models import default_parakeet_directory


class ParakeetSTT(BaseSTT):
    def __init__(self):
        self._lock=threading.Lock()
        self._transcriber=LocalTranscriber(Settings(engine='parakeet',automatic_notes=False,threads=1,
            parakeet_directory=default_parakeet_directory()))

    async def transcribe(self,pcm_bytes:bytes,sample_rate:int=16000)->str:
        if not pcm_bytes:
            return ''
        return await asyncio.to_thread(self._run,pcm_bytes,sample_rate)

    def _run(self,pcm_bytes,sample_rate):
        audio=np.frombuffer(pcm_bytes,dtype='<i2').astype(np.float32)/32768
        audio=to_mono_16k(audio,sample_rate)
        with self._lock:
            return self._transcriber.transcribe(audio)
