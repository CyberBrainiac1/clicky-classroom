"""Independent local ASR; never connects to a running OpenWhispr process."""
from pathlib import Path


class LocalTranscriber:
    def __init__(self, settings):
        self.settings = settings
        self.model = None

    def prepare(self):
        if self.model is not None:
            return
        if self.settings.engine == 'whisper':
            from faster_whisper import WhisperModel
            self.model = WhisperModel(self.settings.whisper_model, device='cpu', compute_type='int8',
                                      cpu_threads=self.settings.threads, num_workers=1, local_files_only=True)
        else:
            import sherpa_onnx
            directory = Path(self.settings.parakeet_directory)
            # Adapted from OpenWhispr parakeetModelInfo.js's transducer manifest.
            names = ['encoder.int8.onnx', 'decoder.int8.onnx', 'joiner.int8.onnx', 'tokens.txt']
            missing = [name for name in names if not (directory/name).is_file()]
            if missing:
                raise ValueError('Parakeet model folder is missing: '+', '.join(missing))
            self.model = sherpa_onnx.OfflineRecognizer.from_transducer(
                encoder=str(directory/names[0]), decoder=str(directory/names[1]),
                joiner=str(directory/names[2]), tokens=str(directory/names[3]),
                model_type='nemo_transducer', num_threads=self.settings.threads,
                sample_rate=16000, feature_dim=80, decoding_method='greedy_search', provider='cpu')

    def transcribe(self, audio):
        self.prepare()
        if self.settings.engine == 'whisper':
            segments, _ = self.model.transcribe(audio, language=self.settings.language or None,
                                                beam_size=3, condition_on_previous_text=False,
                                                vad_filter=True)
            return ' '.join(segment.text.strip() for segment in segments).strip()
        stream = self.model.create_stream()
        stream.accept_waveform(16000, audio)
        self.model.decode_stream(stream)
        return stream.result.text.strip()


def prepare_whisper_download(model='base'):
    """Only a user-invoked Prepare button may download a speech model."""
    from faster_whisper.utils import download_model
    return download_model(model)
