"""No real microphones, loopback devices, active models or cloud services."""
import json
import os
from pathlib import Path
import subprocess
import threading
import time
import wave
import numpy as np
import pytest
from classroom.settings import Settings, validate_local_url
from classroom.session import Session, RATE
from classroom.openwhispr_audio import split_at_pauses, speech_decision
from classroom.notes import LocalNotes, text_chunks
from classroom.recorder import ClassroomRecorder, retry_session, import_audio


@pytest.fixture(autouse=True)
def classroom_isolation(tmp_path, monkeypatch):
    monkeypatch.setenv('CLICKY_CLASSROOM_DATA_DIR', str(tmp_path/'classroom'))


def pcm(seconds=8):
    t = np.arange(int(seconds*RATE))/RATE
    return (.15*np.sin(2*np.pi*220*t)).astype(np.float32)


def write_audio(session, audio, source='microphone'):
    with wave.open(str(session.audio_path(source)), 'wb') as stream:
        stream.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        stream.writeframes((audio*32767).astype('<i2').tobytes())


def wait_until(condition, timeout=5):
    deadline = time.monotonic()+timeout
    while not condition():
        assert time.monotonic() < deadline, 'Timed out waiting for worker'
        time.sleep(.02)


@pytest.mark.parametrize('url', ['https://api.openai.com', 'http://192.168.0.5:8000',
    'http://127.0.0.1.evil.test', 'http://user:pass@localhost', 'http://127.0.0.1/v1', 'ftp://localhost'])
def test_cloud_notes_urls_rejected(url):
    with pytest.raises(ValueError):
        validate_local_url(url)


@pytest.mark.parametrize('url', ['http://127.0.0.1:11434', 'http://localhost:8081', 'http://[::1]:8000'])
def test_local_notes_urls(url):
    assert validate_local_url(url) == url


def test_pause_port_keeps_every_sample_and_cuts_in_quiet_region():
    audio = pcm(65)
    audio[27*RATE:29*RATE] = 0
    pieces = split_at_pauses(audio, max_seconds=30)
    assert np.array_equal(np.concatenate(pieces), audio)
    assert 27*RATE <= len(pieces[0]) <= 29*RATE
    assert max(map(len, pieces)) <= int(30.5*RATE)


def test_openwhispr_speech_gate():
    assert speech_decision(np.zeros(RATE, np.float32)) == (True, 'silence')
    assert speech_decision(pcm(1)) == (False, 'speech_detected')
    assert speech_decision(np.empty(0)) == (False, 'unavailable')


def test_recovery_indexes_wav_tail_once_and_preserves_raw_audio():
    session = Session.create('Physics', Settings(chunk_seconds=5))
    write_audio(session, pcm(12))
    original = session.audio_path('microphone').read_bytes()
    session.add_chunk('microphone', 0, 5*RATE)
    session.finish_chunk(1, 'Newton stated a law.')
    session.retry_and_recover()
    session.retry_and_recover()
    assert [r['frames'] for r in session.rows()] == [5*RATE, 5*RATE, 2*RATE]
    assert session.audio_path('microphone').read_bytes() == original
    assert 'Newton stated' in session.export_transcript()


def test_recorder_pipeline_saves_before_decoding_and_notes_after_stop():
    started = threading.Event()
    calls = []
    class Capture:
        source = 'microphone'
        def run(self, stop, sink, notice):
            sink(self.source, pcm())
            started.set()
            stop.wait()
    class ASR:
        def __init__(self, settings): pass
        def transcribe(self, audio):
            calls.append(len(audio))
            return 'Acceleration is change in velocity over time.'
    class Notes:
        def __init__(self, settings): pass
        def generate(self, session, notify):
            assert session.audio_path('microphone').exists()
            return LocalNotes(Settings(), request=lambda text: '### Key concept\n[00:00:00] Acceleration changes velocity.').generate(session)
    recorder = ClassroomRecorder(Settings(chunk_seconds=5), capture_factory=lambda _: [Capture()],
                                  transcriber_factory=ASR, notes_factory=Notes)
    recorder.start('Physics class')
    assert started.wait(2)
    wait_until(lambda: recorder.session.pending() is not None)
    assert not calls  # deferred mode keeps ASR unloaded while recording
    with wave.open(str(recorder.session.audio_path('microphone')), 'rb') as audio:
        assert audio.getnframes() == 8*RATE  # live WAV header is already readable
    recorder.stop()
    assert recorder.wait_processing(5)
    assert sum(calls) == 8*RATE
    assert 'Acceleration' in (recorder.session.path/'transcript.md').read_text('utf-8')
    assert (recorder.session.path/'notes.md').exists()
    assert Session(recorder.session.path).metadata['status'] == 'complete'


def test_retry_releases_speech_model_before_notes_model_loads():
    import weakref
    refs=[]
    class ASR:
        def __init__(self,settings):refs.append(weakref.ref(self))
        def transcribe(self,audio):return 'Acceleration changes velocity.'
    class Notes:
        def __init__(self,settings):pass
        def generate(self,session,notify):
            assert refs[0]() is None
    session=Session.create('Resource lifecycle',Settings())
    write_audio(session,pcm(1))
    retry_session(session,transcriber_factory=ASR,notes_factory=Notes)
    assert refs[0]() is None


def test_asr_failure_retains_audio_and_retry_does_not_duplicate_transcript():
    session = Session.create('Class', Settings(automatic_notes=False, chunk_seconds=5))
    write_audio(session, pcm(8))
    session.retry_and_recover()
    original = session.audio_path('microphone').read_bytes()
    class Broken:
        def __init__(self, settings): pass
        def transcribe(self, audio): raise RuntimeError('Offline model missing')
    with pytest.raises(RuntimeError):
        retry_session(session, transcriber_factory=Broken)
    assert session.has_errors()
    class Fixed:
        def __init__(self, settings): pass
        def transcribe(self, audio): return 'The derivative is the slope.'
    retry_session(session, transcriber_factory=Fixed)
    retry_session(session, transcriber_factory=Fixed)
    assert len(session.rows()) == 2
    assert session.audio_path('microphone').read_bytes() == original
    assert session.export_transcript().count('The derivative') == 2


def test_capture_failure_is_visible_not_a_successful_class():
    class BrokenCapture:
        source = 'microphone'
        def run(self, stop, sink, notice): raise RuntimeError('Device busy')
    recorder = ClassroomRecorder(Settings(automatic_notes=False), capture_factory=lambda _: [BrokenCapture()])
    recorder.start('Unavailable mic')
    assert recorder.wait_processing(5)
    assert recorder.failure
    assert 'Device busy' in recorder.session.export_transcript()
    assert Session(recorder.session.path).metadata['status'] == 'needs-review'


def test_long_notes_cover_all_sections_cache_and_retry():
    session = Session.create('Long class', Settings())
    for index in range(8):
        session.add_chunk('microphone', index*30*RATE, 30*RATE)
        session.finish_chunk(index+1, f'Topic {index}: '+('Explain angular velocity. '*150))
    requests = []
    def request(text):
        requests.append(text)
        return '### Topic notes\n'+text[:150]
    engine = LocalNotes(Settings(), request=request)
    engine.generate(session)
    assert len(requests) >= 2
    assert all(len(text) < 10200 for text in requests)
    assert 'Topic 7' in ''.join(requests)
    engine.generate(session)
    assert len(requests) == len(list((session.path/'notes-parts').glob('*.md')))
    assert 'Class section' in (session.path/'notes.md').read_text('utf-8')


def test_local_http_notes_request_and_cloud_redirect_not_followed():
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    captured = []
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            captured.append((self.path, json.loads(self.rfile.read(int(self.headers['Content-Length'])))))
            if self.path == '/api/chat':
                payload = json.dumps({'message': {'content': '## Key ideas\n[00:00:00] Newton.'},'done':True}).encode()
                self.send_response(200)
                self.send_header('Content-Type','application/json')
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(302)
                self.send_header('Location','https://example.invalid')
                self.end_headers()
        def log_message(self, *args): pass
    server = ThreadingHTTPServer(('127.0.0.1',0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        settings = Settings(notes_url=f'http://127.0.0.1:{server.server_port}')
        assert 'Newton' in LocalNotes(settings)._request('[00:00:00] Newton.')
        assert captured[0][0] == '/api/chat'
        assert captured[0][1]['options']['num_ctx'] == 8192
        settings.notes_backend = 'openai-local'
        import httpx
        with pytest.raises(httpx.HTTPStatusError):
            LocalNotes(settings)._request('Never send this elsewhere')
    finally:
        server.shutdown()
        server.server_close()


def test_import_synthetic_wav_does_not_open_devices(tmp_path, monkeypatch):
    source = tmp_path/'input.wav'
    import soundfile as sf
    sf.write(source, pcm(2), RATE)
    monkeypatch.setattr('classroom.recorder.make_captures', lambda _: pytest.fail('No live capture allowed'))
    session = import_audio(source, 'Imported class', Settings(automatic_notes=False))
    assert session.audio_path('import').exists()
    assert len(session.rows()) == 1
    assert session.rows()[0]['frames'] == 2*RATE


def test_ui_open_has_no_microphone_or_model_side_effects(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtWidgets import QApplication
    from classroom.ui import ClassroomWindow
    monkeypatch.setattr('classroom.ui.ClassroomRecorder', lambda *a, **k: pytest.fail('Opening UI must not record'))
    app = QApplication.instance() or QApplication([])
    window = ClassroomWindow()
    window.show()
    app.processEvents()
    assert window.recorder is None
    assert window.session is None
    assert not window.stop_button.isEnabled()
    assert window.start_button.isEnabled()
    window.close()
    app.processEvents()


def test_ui_background_job_does_not_touch_live_capture(monkeypatch):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    from PyQt6.QtWidgets import QApplication
    from classroom.ui import ClassroomWindow
    app = QApplication.instance() or QApplication([])
    window = ClassroomWindow()
    results = []
    window._job(lambda:42,results.append)
    deadline=time.monotonic()+3
    while window.jobs and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.01)
    assert results == [42]
    assert not window.jobs
    assert window.recorder is None
    window.close()


def test_speech_adapters_are_cpu_only_offline_and_do_not_use_openwhispr_server(monkeypatch,tmp_path):
    from types import SimpleNamespace
    import sys
    from classroom.engines import LocalTranscriber
    calls=[]
    class Whisper:
        def __init__(self,*args,**kwargs):calls.append(kwargs)
        def transcribe(self,*args,**kwargs):return iter([SimpleNamespace(text='Local speech')]),None
    monkeypatch.setitem(sys.modules,'faster_whisper',SimpleNamespace(WhisperModel=Whisper))
    assert LocalTranscriber(Settings(engine='whisper',threads=1)).transcribe(pcm(1)) == 'Local speech'
    assert calls[0]['local_files_only'] is True
    assert calls[0]['device'] == 'cpu' and calls[0]['cpu_threads'] == 1
    for name in ['encoder.int8.onnx','decoder.int8.onnx','joiner.int8.onnx','tokens.txt']:
        (tmp_path/name).write_bytes(b'test model placeholder')
    class Recognizer:
        @staticmethod
        def from_transducer(**kwargs):
            calls.append(kwargs)
            return SimpleNamespace(create_stream=lambda:SimpleNamespace(
                accept_waveform=lambda *a:None,result=SimpleNamespace(text='Parakeet speech')),
                decode_stream=lambda stream:None)
    monkeypatch.setitem(sys.modules,'sherpa_onnx',SimpleNamespace(OfflineRecognizer=Recognizer))
    value=LocalTranscriber(Settings(engine='parakeet',parakeet_directory=str(tmp_path)))
    assert value.transcribe(pcm(1)) == 'Parakeet speech'
    assert calls[-1]['model_type'] == 'nemo_transducer'
    assert calls[-1]['provider'] == 'cpu'
    assert Path(calls[-1]['tokens']).parent == tmp_path
