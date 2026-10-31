"""Copy local OpenWhispr notes without changing the source or importing secrets."""
from datetime import datetime, timezone
from contextlib import closing
import hashlib
import json
import math
import os
from pathlib import Path
import sqlite3
import tempfile

from .session import Session, RATE
from .settings import Settings, atomic_text, data_root

FIELDS = ('id','client_note_id','title','content','enhanced_content','transcript',
          'created_at','updated_at','note_type','folder_id','audio_duration_seconds',
          'participants','diarization_enabled','source_file','enhancement_prompt','enhancement_template_id')


def default_database():
    return Path(os.getenv('APPDATA',Path.home()/'AppData/Roaming'))/'open-whispr/transcriptions.db'


def _number(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value):
        return float(value)
    return None


def transcript_rows(raw):
    """Preserve source text and known times; epoch-ms times follow OW's rebasing."""
    if not raw:
        return [],[],None
    try:
        parsed=json.loads(raw)
    except (ValueError,TypeError):
        parsed=None
    if not isinstance(parsed,list) or not all(isinstance(s,dict) and isinstance(s.get('text'),str) for s in parsed):
        # Legacy text or an unknown JSON format is kept verbatim, never dropped.
        return [(0,'import',0,0,str(raw))],[1],None
    times=[_number(s.get('timestamp')) for s in parsed]
    epoch=[t for t in times if t is not None and t>1e9]
    origin=min(epoch) if epoch else None
    rows,untimed=[],[]
    for index,segment in enumerate(parsed):
        time=times[index]
        known=time is not None and time>=0
        start=max(0,(time-origin)/1000 if time>1e9 and origin is not None else time) if known else 0
        source={'mic':'microphone','microphone':'microphone','system':'system'}.get(segment.get('source'),'import')
        text=segment['text']
        speaker=segment.get('speakerName')
        if not isinstance(speaker,str) or not speaker.strip():
            speaker=segment.get('speaker')
            if isinstance(speaker,str) and speaker.startswith('speaker_') and speaker[8:].isdigit():
                speaker='Speaker '+str(int(speaker[8:])+1)
        if isinstance(speaker,str) and speaker.strip():
            text='['+speaker.strip()+'] '+text
        # No audio is copied. Ordinals avoid collisions between equal timestamps;
        # zero duration avoids inventing an end time not supplied by OpenWhispr.
        rows.append((index,source,start,0,text))
        if not known:
            untimed.append(index+1)
    return rows,untimed,origin


def _created(value):
    try:
        parsed=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if parsed.tzinfo is None:
            parsed=parsed.replace(tzinfo=timezone.utc)  # SQLite CURRENT_TIMESTAMP
        return parsed.isoformat()
    except (ValueError,TypeError):
        return datetime.now(timezone.utc).isoformat()


def import_openwhispr_notes(database=None):
    database=Path(database or default_database()).resolve()
    if not database.is_file():
        raise FileNotFoundError('OpenWhispr local notes database was not found.')
    # Read the WAL-aware current database through SQLite, not a stale file copy.
    with closing(sqlite3.connect(database.as_uri()+'?mode=ro',uri=True,timeout=5)) as source:
        source.row_factory=sqlite3.Row
        source.execute('PRAGMA query_only=ON')
        source.execute('BEGIN')
        columns={row['name'] for row in source.execute('PRAGMA table_info(notes)')}
        if not {'id','title','content'}<=columns:
            raise ValueError('This is not a supported OpenWhispr notes database.')
        where=[]
        if 'deleted_at' in columns:
            where.append('deleted_at IS NULL')
        if 'left_team' in columns:
            where.append('COALESCE(left_team,0)=0')
        selected=[field for field in FIELDS if field in columns]
        query='SELECT '+','.join(selected)+' FROM notes'+(' WHERE '+' AND '.join(where) if where else '')+' ORDER BY id'
        notes=[dict(row) for row in source.execute(query)]
        excluded=source.execute('SELECT COUNT(*) FROM notes').fetchone()[0]-len(notes)
        folders={}
        if source.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='folders'").fetchone():
            folders={row['id']:row['name'] for row in source.execute('SELECT id,name FROM folders')}
        source.rollback()
    root=data_root().resolve()
    sessions=root/'sessions'
    sessions.mkdir(parents=True,exist_ok=True)
    staging=root/'import-staging'
    staging.mkdir(exist_ok=True)
    result={'imported':[],'alreadyImported':0,'changedSourceKept':0,'excluded':excluded,'errors':[]}
    for note in notes:
        try:
            identity=str(note.get('client_note_id') or str(database).casefold()+':'+str(note['id']))
            key=hashlib.sha256(('openwhispr:'+identity).encode()).hexdigest()
            raw=json.dumps(note,ensure_ascii=False,sort_keys=True)
            fingerprint=hashlib.sha256(raw.encode()).hexdigest()
            target=sessions/('openwhispr-'+key[:32])
            if target.exists():
                existing=Session(target).metadata.get('origin',{})
                if existing.get('key')!=key:
                    raise FileExistsError('Import destination belongs to another note; nothing was overwritten.')
                result['alreadyImported']+=1
                result['changedSourceKept']+=int(existing.get('fingerprint')!=fingerprint)
                continue
            rows,untimed,epoch=transcript_rows(note.get('transcript'))
            with tempfile.TemporaryDirectory(prefix='openwhispr-',dir=staging) as temporary:
                temp=Path(temporary).resolve()
                if temp.parent!=staging.resolve():
                    raise ValueError('Import staging escaped its data directory.')
                session=Session.create(note.get('title') or 'Untitled note',Settings(automatic_notes=False),directory=temp/'note')
                session.metadata.update({'created':_created(note.get('created_at')),'status':'imported-note',
                    'folder':folders.get(note.get('folder_id')) or 'OpenWhispr',
                    'transcript_only':True,'untimed_chunk_ids':untimed,
                    'origin':{'app':'OpenWhispr','key':key,'fingerprint':fingerprint,'note_id':note['id'],
                              'source_updated':note.get('updated_at'),'epoch_origin_ms':epoch}})
                with session.db() as db:
                    db.executemany("INSERT INTO chunks(first_frame,source,start_seconds,frames,text,status) VALUES(?,?,?,?,?,'done')",rows)
                content=note.get('content') or ''
                summary=note.get('enhanced_content') or ''
                parts=[]
                if content:
                    parts.append(content)
                    atomic_text(session.path/'openwhispr-personal-notes.md',content)
                if summary:
                    parts.append(('## OpenWhispr summary\n\n' if content else '')+summary)
                    atomic_text(session.path/'openwhispr-summary.md',summary)
                if parts:
                    atomic_text(session.path/'notes.md','\n\n'.join(parts))
                atomic_text(session.path/'openwhispr-original.json',raw)
                atomic_text(session.path/'session.json',json.dumps(session.metadata,ensure_ascii=False,indent=2))
                session.export_transcript()
                # Make incomplete imports invisible; publish each complete note once.
                session.path.rename(target)
            result['imported'].append(str(target))
        except Exception as exc:
            result['errors'].append({'note_id':note.get('id'),'error':str(exc)})
    return result
