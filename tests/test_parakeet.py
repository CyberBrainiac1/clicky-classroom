import asyncio
import io
from pathlib import Path
import tarfile
from types import SimpleNamespace
import numpy as np
import pytest


@pytest.fixture(autouse=True)
def isolate(tmp_path,monkeypatch):
    monkeypatch.setenv('CLICKY_CLASSROOM_DATA_DIR',str(tmp_path/'classroom'))
    monkeypatch.delenv('CLICKY_PARAKEET_MODEL',raising=False)


def test_new_classroom_defaults_to_own_parakeet_cache():
    from classroom.settings import Settings,data_root
    from classroom.models import default_parakeet_directory
    settings=Settings()
    assert settings.engine == 'parakeet'
    assert Path(settings.parakeet_directory) == data_root()/'models'/'parakeet-tdt-0.6b-v3'
    assert settings.parakeet_directory == default_parakeet_directory()
    assert not data_root().exists()  # defaults only; no capture/download/config writes


def test_ready_cache_never_downloads_or_changes_files(monkeypatch):
    from classroom import models
    path=Path(models.default_parakeet_directory())
    path.mkdir(parents=True)
    for name in models.PARAKEET_FILES:
        (path/name).write_bytes(b'unchanged-model')
    before={p.name:p.read_bytes() for p in path.iterdir()}
    monkeypatch.setattr(models.urllib.request,'urlopen',lambda *a,**k:pytest.fail('No download for an existing cache'))
    assert models.prepare_parakeet_download() == str(path)
    assert {p.name:p.read_bytes() for p in path.iterdir()} == before


@pytest.mark.parametrize('bad_member',[None,'../../encoder.int8.onnx'])
def test_model_download_extracts_only_regular_expected_weights(monkeypatch,bad_member):
    from classroom import models
    compressed=io.BytesIO()
    with tarfile.open(fileobj=compressed,mode='w:bz2') as archive:
        for index,name in enumerate(models.PARAKEET_FILES):
            path=bad_member if bad_member and index==0 else 'model/'+name
            info=tarfile.TarInfo(path)
            payload=b'placeholder-test-weights'
            info.size=len(payload)
            archive.addfile(info,io.BytesIO(payload))
    class Response(io.BytesIO):
        url='https://release-assets.githubusercontent.com/model'
    monkeypatch.setattr(models.urllib.request,'urlopen',lambda *a,**k:Response(compressed.getvalue()))
    if bad_member:
        with pytest.raises(ValueError):models.prepare_parakeet_download()
        assert not Path(models.default_parakeet_directory()).exists()
    else:
        path=Path(models.prepare_parakeet_download())
        assert models.model_ready(path)
        assert {p.name for p in path.iterdir()} == set(models.PARAKEET_FILES)


def test_regular_clicky_parakeet_adapter_accepts_pcm_without_devices(monkeypatch):
    import audio.stt.parakeet_stt as module
    calls=[]
    class Transcriber:
        def __init__(self,settings):
            assert settings.engine == 'parakeet'
            assert settings.threads == 1
        def transcribe(self,audio):
            calls.append(audio)
            return 'Teacher explains acceleration.'
    monkeypatch.setattr(module,'LocalTranscriber',Transcriber)
    recognizer=module.ParakeetSTT()
    raw=(np.sin(np.arange(48000)/20)*4000).astype('<i2').tobytes()
    assert asyncio.run(recognizer.transcribe(raw,48000)) == 'Teacher explains acceleration.'
    assert len(calls[0]) == 16000
    assert asyncio.run(recognizer.transcribe(b'')) == ''


def test_regular_clicky_auto_selects_ready_parakeet_and_respects_explicit_provider(monkeypatch):
    from config import cfg
    from classroom import models
    path=Path(models.default_parakeet_directory())
    path.mkdir(parents=True)
    for name in models.PARAKEET_FILES:(path/name).write_bytes(b'fixture')
    monkeypatch.delenv('CLICKY_STT',raising=False)
    assert cfg.stt_provider() == 'parakeet'
    monkeypatch.setenv('CLICKY_STT','faster_whisper')
    assert cfg.stt_provider() == 'faster_whisper'
    monkeypatch.setenv('CLICKY_STT','parakeet')
    assert cfg.stt_provider() == 'parakeet'
