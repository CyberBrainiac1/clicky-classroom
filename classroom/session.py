"""Durable lecture audio, recoverable chunk jobs and timestamped transcripts."""
from dataclasses import asdict
from contextlib import contextmanager
from datetime import datetime
import json
from pathlib import Path
import re
import sqlite3
import uuid
import wave
import numpy as np
from .settings import atomic_text, data_root, Settings

RATE = 16000


def stamp(seconds):
    seconds = max(0, int(seconds))
    return f'{seconds//3600:02}:{seconds//60%60:02}:{seconds%60:02}'


class Session:
    def __init__(self, path):
        self.path = Path(path)
        self.metadata = json.loads((self.path/'session.json').read_text('utf-8'))

    @classmethod
    def create(cls, title, settings, *, directory=None):
        settings.validate()
        slug = re.sub(r'[^\w -]', '', title).strip()[:60] or 'Class'
        path = Path(directory) if directory is not None else data_root()/'sessions'/(datetime.now().strftime('%Y%m%d-%H%M%S')+'-'+slug+'-'+uuid.uuid4().hex[:6])
        if directory is not None and not path.resolve().is_relative_to(data_root().resolve()):
            raise ValueError('Session staging must stay inside Clicky Classroom data.')
        path.mkdir(parents=True)
        atomic_text(path/'session.json', json.dumps({'title': title or 'Class', 'created': datetime.now().isoformat(),
                                                    'settings': asdict(settings), 'status': 'recording'}, indent=2))
        obj = cls(path)
        with obj.db() as db:
            db.executescript('''
                CREATE TABLE chunks (id INTEGER PRIMARY KEY, source TEXT NOT NULL,
                    first_frame INTEGER NOT NULL, frames INTEGER NOT NULL,
                    start_seconds REAL NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                    text TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    UNIQUE(source,first_frame));
                CREATE TABLE events (id INTEGER PRIMARY KEY, kind TEXT, message TEXT);
            ''')
        obj.export_transcript()
        return obj

    @contextmanager
    def db(self):
        connection = sqlite3.connect(self.path/'session.sqlite3', timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    @property
    def settings(self):
        return Settings(**self.metadata['settings'])

    def set_status(self, status):
        self.metadata['status'] = status
        atomic_text(self.path/'session.json', json.dumps(self.metadata, indent=2))

    def audio_path(self, source):
        if source not in {'microphone', 'system', 'import'}:
            raise ValueError('Unknown audio source')
        return self.path/f'audio-{source}.wav'

    def add_chunk(self, source, first_frame, frames):
        if frames <= 0:
            return
        with self.db() as db:
            db.execute('INSERT OR IGNORE INTO chunks(source,first_frame,frames,start_seconds) VALUES(?,?,?,?)',
                       (source, int(first_frame), int(frames), first_frame/RATE))

    def pending(self):
        with self.db() as db:
            row = db.execute("SELECT * FROM chunks WHERE status='pending' ORDER BY start_seconds,id LIMIT 1").fetchone()
        return dict(row) if row else None

    def rows(self):
        with self.db() as db:
            order='id' if self.metadata.get('transcript_only') else 'start_seconds,id'
            return [dict(row) for row in db.execute('SELECT * FROM chunks ORDER BY '+order)]

    def finish_chunk(self, id_, text='', error='', status='done'):
        with self.db() as db:
            db.execute('UPDATE chunks SET status=?,text=?,error=? WHERE id=?', (status, text, error, id_))
        self.export_transcript()

    def event(self, kind, message):
        with self.db() as db:
            db.execute('INSERT INTO events(kind,message) VALUES(?,?)', (kind, str(message)))

    def read_chunk(self, chunk):
        with wave.open(str(self.audio_path(chunk['source'])), 'rb') as audio:
            if audio.getframerate() != RATE or audio.getnchannels() != 1 or audio.getsampwidth() != 2:
                raise ValueError('Expected16kHz mono PCM16 session audio')
            audio.setpos(chunk['first_frame'])
            raw = audio.readframes(chunk['frames'])
        if len(raw) != chunk['frames']*2:
            raise ValueError('Audio chunk is truncated; recording retained for recovery')
        return np.frombuffer(raw, dtype='<i2').astype(np.float32)/32768

    def retry_and_recover(self, chunk_seconds=None):
        """Index an interrupted capture's durable WAV tail without recording anew."""
        size = int((chunk_seconds or self.settings.chunk_seconds)*RATE)
        with self.db() as db:
            db.execute("UPDATE chunks SET status='pending',error='' WHERE status='error'")
        for source in ['microphone', 'system', 'import']:
            path = self.audio_path(source)
            if not path.exists():
                continue
            with wave.open(str(path), 'rb') as audio:
                total = audio.getnframes()
            with self.db() as db:
                end = db.execute('SELECT MAX(first_frame+frames) FROM chunks WHERE source=?', (source,)).fetchone()[0] or 0
            while end < total:
                frames = min(size, total-end)
                self.add_chunk(source, end, frames)
                end += frames

    def export_transcript(self):
        lines = ['# '+self.metadata['title'], '', 'Timestamped local transcript. ASR can mishear names, numbers and equations.', '']
        for row in self.rows():
            label = (('[Time not supplied]' if row['id'] in self.metadata.get('untimed_chunk_ids',[]) else f"[{stamp(row['start_seconds'])}]" if self.metadata.get('transcript_only') else f"[{stamp(row['start_seconds'])}–{stamp(row['start_seconds']+row['frames']/RATE)}]")+' '+row['source'])
            if row['status'] == 'done' and row['text']:
                lines.extend(['## '+label, row['text'], ''])
            elif row['status'] in {'pending', 'error'}:
                lines.extend(['## '+label, '[Transcription pending]' if row['status'] == 'pending' else '[Transcription failed: '+row['error']+']', ''])
        with self.db() as db:
            events = list(db.execute('SELECT kind,message FROM events ORDER BY id'))
        if events:
            lines.extend(['## Recording notices', ''])
            lines.extend('- '+row['kind']+': '+row['message'] for row in events)
        text = '\n'.join(lines)+'\n'
        atomic_text(self.path/'transcript.md', text)
        return text

    def notes_input(self):
        return '\n'.join(('['+('Time not supplied' if r['id'] in self.metadata.get('untimed_chunk_ids',[]) else stamp(r['start_seconds']))+f"] ({r['source']}) {r['text']}") for r in self.rows()
                         if r['status'] == 'done' and r['text'])

    def has_errors(self):
        with self.db() as db:
            issues = db.execute("SELECT COUNT(*) FROM events WHERE kind IN ('audio_gap','capture_error','storage_error','input_overflow')").fetchone()[0]
        return bool(issues) or any(r['status'] in {'error', 'pending'} for r in self.rows())
