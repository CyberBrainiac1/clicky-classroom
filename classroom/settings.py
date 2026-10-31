from dataclasses import asdict, dataclass, field
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit


def data_root() -> Path:
    explicit = os.getenv('CLICKY_CLASSROOM_DATA_DIR')
    return Path(explicit) if explicit else Path(os.getenv('LOCALAPPDATA', str(Path.home()))) / 'ClickyClassroom'


def atomic_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=path.name+'.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@dataclass
class Settings:
    source: str = 'microphone'
    microphone_device: int | None = None
    engine: str = 'parakeet'
    whisper_model: str = 'base'
    parakeet_directory: str = field(default_factory=lambda: str(Path(os.getenv('CLICKY_PARAKEET_MODEL')) if os.getenv('CLICKY_PARAKEET_MODEL') else data_root()/'models'/'parakeet-tdt-0.6b-v3'))
    language: str = 'en'
    threads: int = 2
    chunk_seconds: int = 30
    live_transcription: bool = False
    notes_backend: str = 'ollama'
    notes_url: str = 'http://127.0.0.1:11434'
    notes_model: str = 'qwen3.5:4b'
    automatic_notes: bool = True

    def validate(self):
        if self.source not in {'microphone', 'system', 'both'}:
            raise ValueError('Choose microphone, system audio, or both.')
        if self.engine not in {'whisper', 'parakeet'}:
            raise ValueError('Choose a supported local speech engine.')
        if not 1 <= self.threads <= 4 or not 5 <= self.chunk_seconds <= 60:
            raise ValueError('CPU threads must be1–4; chunks must be5–60seconds.')
        if self.notes_backend not in {'ollama', 'openai-local'}:
            raise ValueError('Choose Ollama or a local OpenAI-compatible notes server.')
        validate_local_url(self.notes_url)
        if not self.notes_model.strip():
            raise ValueError('Choose a local notes model.')

    @classmethod
    def load(cls):
        path = data_root() / 'settings.json'
        return cls(**json.loads(path.read_text('utf-8'))) if path.exists() else cls()

    def save(self):
        self.validate()
        atomic_text(data_root() / 'settings.json', json.dumps(asdict(self), indent=2))


def validate_local_url(value: str) -> str:
    parsed = urlsplit(value)
    if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost', '::1'}:
        raise ValueError('Class notes stay local: use an http://127.0.0.1, localhost, or [::1] server.')
    if parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {'', '/'}:
        raise ValueError('Enter only the local server base URL, without credentials or a path.')
    # Accessing port validates malformed port numbers as well.
    _ = parsed.port
    return value.rstrip('/')
