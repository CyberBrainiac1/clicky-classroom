"""Independent capture/spooling/ASR workers; no active OpenWhispr integration."""
import os
import queue
import threading
import time
import wave
import numpy as np
from .capture import make_captures, to_mono_16k
from .engines import LocalTranscriber
from .notes import LocalNotes
from .openwhispr_audio import split_at_pauses, speech_decision
from .session import Session, RATE


class ClassroomRecorder:
    def __init__(self, settings, notify=lambda message: None, capture_factory=make_captures,
                 transcriber_factory=LocalTranscriber, notes_factory=LocalNotes):
        self.settings, self.notify = settings, notify
        self.capture_factory, self.transcriber_factory = capture_factory, transcriber_factory
        self.notes_factory = notes_factory
        self.session = None
        self.stop_capture = threading.Event()
        self.writer_done = threading.Event()
        self.frames = queue.Queue(maxsize=128)
        self.capture_threads = []
        self.writer_thread = self.asr_thread = None
        self.started = False
        self.failure = None

    def start(self, title):
        if self.started:
            raise RuntimeError('This recorder has already started.')
        self.settings.validate()
        captures = self.capture_factory(self.settings)
        if not captures:
            raise ValueError('Choose at least one audio source.')
        self.session = Session.create(title, self.settings)
        self.started = True
        self.writer_thread = threading.Thread(target=self._write, daemon=True, name='classroom-spool')
        self.asr_thread = threading.Thread(target=self._transcribe, daemon=True, name='classroom-asr')
        self.writer_thread.start()
        self.asr_thread.start()
        self.capture_threads = [threading.Thread(target=self._capture, args=(capture,), daemon=True,
                                                 name='classroom-'+capture.source) for capture in captures]
        for thread in self.capture_threads:
            thread.start()
        self.notify('Recording class audio. Stop when the class ends.')
        return self.session.path

    @property
    def recording(self):
        return self.started and not self.stop_capture.is_set()

    def _sink(self, source, audio):
        if not len(audio):
            return
        try:
            self.frames.put_nowait((source, np.asarray(audio, dtype=np.float32).copy()))
        except queue.Full:
            self.session.event('audio_gap', f'{source}: recorder fell behind; {len(audio)/RATE:.2f}s could not be queued.')
            self.failure = 'Audio buffer overflow. Stopped capture to avoid silently losing more audio.'
            self.stop_capture.set()
            self.notify(self.failure)

    def _capture(self, capture):
        try:
            capture.run(self.stop_capture, self._sink, self.session.event)
        except Exception as exc:
            self.failure = f'{capture.source} capture stopped: {exc}'
            self.session.event('capture_error', self.failure)
            self.stop_capture.set()
            self.notify(self.failure)

    def _write(self):
        writers, handles, buffers, offsets, total = {}, {}, {}, {}, {}
        began = time.monotonic()
        try:
            while True:
                try:
                    source, audio = self.frames.get(timeout=.2)
                except queue.Empty:
                    if self.stop_capture.is_set() and not any(t.is_alive() for t in self.capture_threads):
                        break
                    continue
                if source not in writers:
                    handle = open(self.session.audio_path(source), 'wb')
                    writer = wave.open(handle, 'wb')
                    writer.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
                    writers[source], handles[source] = writer, handle
                    buffers[source], offsets[source], total[source] = np.empty(0, np.float32), 0, 0
                raw = (np.clip(audio, -1, 1)*32767).astype('<i2').tobytes()
                writers[source].writeframes(raw)  # updates WAV header on each block
                handles[source].flush()
                total[source] += len(audio)
                buffers[source] = np.concatenate([buffers[source], audio])
                threshold = int((self.settings.chunk_seconds+.5)*RATE)
                if len(buffers[source]) > threshold:
                    pieces = split_at_pauses(buffers[source], RATE, self.settings.chunk_seconds)
                    for piece in pieces[:-1]:
                        os.fsync(handles[source].fileno())
                        self.session.add_chunk(source, offsets[source], len(piece))
                        offsets[source] += len(piece)
                    buffers[source] = pieces[-1].copy()
                self.frames.task_done()
                if time.monotonic()-began > 8*3600:
                    self.session.event('duration_limit', 'Eight-hour limit reached; start a new session for more audio.')
                    self.stop_capture.set()
        except Exception as exc:
            self.failure = 'Saving audio failed: '+str(exc)
            self.session.event('storage_error', self.failure)
            self.stop_capture.set()
            self.notify(self.failure)
        finally:
            for source, writer in writers.items():
                try:
                    writer.close()
                    handles[source].flush()
                    os.fsync(handles[source].fileno())
                    handles[source].close()
                    # Final tail is durable before it is published for ASR.
                    self.session.add_chunk(source, offsets[source], total[source]-offsets[source])
                except Exception as exc:
                    self.failure = 'Final audio flush failed: '+str(exc)
                    self.session.event('storage_error', self.failure)
            self.session.set_status('needs-review' if self.failure else 'processing')
            self.writer_done.set()

    def _transcribe(self):
        try:
            transcriber = self.transcriber_factory(self.settings)
            if not self.settings.live_transcription:
                self.writer_done.wait()
            while True:
                chunk = self.session.pending()
                if chunk is None:
                    if self.writer_done.is_set():
                        break
                    time.sleep(.2)
                    continue
                try:
                    audio = self.session.read_chunk(chunk)
                    skip, reason = speech_decision(audio)
                    text = '' if skip else transcriber.transcribe(audio)
                    self.session.finish_chunk(chunk['id'], text=text, status='silence' if skip else 'done')
                    self.notify(f"Transcribed {chunk['start_seconds']:.0f}s ({chunk['source']})" if not skip else f'Skipped {reason}')
                except Exception as exc:
                    self.session.finish_chunk(chunk['id'], error=str(exc), status='error')
                    self.notify('Transcription paused: '+str(exc)+'. Audio remains saved; use Retry after setup.')
                    # Preserve the remaining queue instead of repeatedly loading a failing model.
                    self.writer_done.wait()
                    break
            self.session.export_transcript()
            del transcriber  # release ASR weights before loading a notes model
            self.session.set_status('needs-review' if self.failure else 'needs-transcription' if self.session.has_errors() else 'transcribed')
            if self.settings.automatic_notes and self.session.notes_input():
                try:
                    self.notes_factory(self.settings).generate(self.session, self.notify)
                    self.session.set_status('complete-with-gaps' if self.session.has_errors() or self.failure else 'complete')
                except Exception as exc:
                    self.session.event('notes_pending', str(exc))
                    self.session.set_status('notes-pending')
                    self.notify('Transcript saved; local notes are pending: '+str(exc))
            self.notify('Class saved: '+str(self.session.path))
        except Exception as exc:
            self.failure = str(exc)
            self.session.event('processing_error', str(exc))
            self.session.set_status('needs-processing')
            self.notify('Class audio is saved. Processing error: '+str(exc))

    def stop(self, wait=True):
        self.stop_capture.set()
        if wait:
            for thread in self.capture_threads:
                thread.join(timeout=5)
            if any(thread.is_alive() for thread in self.capture_threads):
                raise RuntimeError('Audio device is still closing. Keep Clicky open and try Stop again.')
            if self.writer_thread:
                self.writer_thread.join(timeout=10)
                if self.writer_thread.is_alive():
                    raise RuntimeError('Audio is still saving. Keep Clicky open.')
        return self.session.path if self.session else None

    def wait_processing(self, timeout=None):
        if self.asr_thread:
            self.asr_thread.join(timeout)
        return not self.asr_thread or not self.asr_thread.is_alive()


def retry_session(session, notify=lambda message: None, transcriber_factory=LocalTranscriber, notes_factory=LocalNotes,
                  settings=None):
    settings = settings or session.settings
    settings.validate()
    session.retry_and_recover(settings.chunk_seconds)
    transcriber = transcriber_factory(settings)
    while (chunk := session.pending()) is not None:
        try:
            audio = session.read_chunk(chunk)
            skip, _ = speech_decision(audio)
            text = '' if skip else transcriber.transcribe(audio)
            session.finish_chunk(chunk['id'], text=text, status='silence' if skip else 'done')
            notify('Transcription updated')
        except Exception as exc:
            session.finish_chunk(chunk['id'], error=str(exc), status='error')
            raise
    session.export_transcript()
    del transcriber  # release ASR weights before loading a notes model
    if settings.automatic_notes and session.notes_input():
        try:
            notes_factory(settings).generate(session, notify)
        except Exception:
            session.set_status('notes-pending')
            raise
    session.set_status('complete-with-gaps' if session.has_errors() else 'complete')


def import_audio(path, title, settings, notify=lambda message: None):
    """Import a file explicitly selected by the user; no live devices are touched."""
    import soundfile as sf
    session = Session.create(title, settings)
    with sf.SoundFile(path) as source, wave.open(str(session.audio_path('import')), 'wb') as output:
        output.setparams((1, 2, RATE, 0, 'NONE', 'not compressed'))
        for block in source.blocks(blocksize=source.samplerate, dtype='float32', always_2d=True):
            mono = to_mono_16k(block, source.samplerate, source.channels)
            output.writeframes((mono*32767).astype('<i2').tobytes())
    session.retry_and_recover()
    session.set_status('needs-transcription')
    return session
