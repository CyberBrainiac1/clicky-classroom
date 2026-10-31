import hashlib
import json
from pathlib import Path
import sqlite3
import pytest
from classroom.openwhispr_import import import_openwhispr_notes,transcript_rows
from classroom.session import Session
from classroom.settings import data_root,atomic_text


@pytest.fixture(autouse=True)
def isolated(tmp_path,monkeypatch):
    monkeypatch.setenv('CLICKY_CLASSROOM_DATA_DIR',str(tmp_path/'clicky'))
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')


def database(tmp_path,wal=False):
    path=tmp_path/'OpenWhispr.db'
    connection=sqlite3.connect(path)
    if wal:
        connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript('''CREATE TABLE notes (
        id INTEGER PRIMARY KEY,title TEXT,content TEXT,enhanced_content TEXT,transcript TEXT,
        created_at TEXT,updated_at TEXT,client_note_id TEXT,folder_id INTEGER,
        deleted_at TEXT,left_team INTEGER DEFAULT 0,share_token TEXT);
        CREATE TABLE folders (id INTEGER,name TEXT);
        INSERT INTO folders VALUES(1,'Physics');''')
    connection.commit()
    return path,connection


def insert(connection,id=1,**changes):
    values=dict(id=id,title='Energy',content='My derivation',enhanced_content='Energy summary',
        transcript=json.dumps([{'text':'Kinetic energy is half m v squared.','source':'system','timestamp':10.5,'speaker':'speaker_0'}]),
        created_at='2026-10-31 18:00:00',updated_at='2026-10-31 19:00:00',client_note_id='note-'+str(id),
        folder_id=1,deleted_at=None,left_team=0,share_token='DO_NOT_IMPORT_THIS_TOKEN')
    values.update(changes)
    connection.execute('INSERT INTO notes('+','.join(values)+') VALUES('+','.join('?' for _ in values)+')',list(values.values()))
    connection.commit()


def test_wal_import_preserves_notes_summaries_dates_and_source_bytes(tmp_path):
    path,writer=database(tmp_path,wal=True)
    insert(writer)
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [path,Path(str(path)+'-wal')]}
    result=import_openwhispr_notes(path)
    assert len(result['imported'])==1 and not result['errors']
    session=Session(result['imported'][0])
    assert session.metadata['folder']=='Physics'
    assert session.metadata['created']=='2026-10-31T18:00:00+00:00'
    assert 'My derivation' in (session.path/'notes.md').read_text('utf-8')
    assert 'Energy summary' in (session.path/'notes.md').read_text('utf-8')
    assert session.rows()[0]['start_seconds']==10.5
    assert session.rows()[0]['text'].startswith('[Speaker 1]')
    assert not list(session.path.glob('*.wav'))
    raw=(session.path/'openwhispr-original.json').read_text('utf-8')
    assert 'DO_NOT_IMPORT_THIS_TOKEN' not in raw and 'share_token' not in raw
    assert {p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [path,Path(str(path)+'-wal')]}==before
    writer.close()


def test_reimport_never_duplicates_or_overwrites_clicky_edits(tmp_path):
    path,connection=database(tmp_path)
    insert(connection)
    session=Session(import_openwhispr_notes(path)['imported'][0])
    atomic_text(session.path/'notes.md','My Clicky edits')
    connection.execute("UPDATE notes SET content='New source content'")
    connection.commit()
    result=import_openwhispr_notes(path)
    assert not result['imported'] and result['alreadyImported']==1 and result['changedSourceKept']==1
    assert (session.path/'notes.md').read_text('utf-8')=='My Clicky edits'
    assert len(list((data_root()/'sessions').iterdir()))==1
    connection.close()


def test_deleted_and_revoked_team_notes_are_not_imported(tmp_path):
    path,connection=database(tmp_path)
    insert(connection,id=1)
    insert(connection,id=2,deleted_at='2026-10-31')
    insert(connection,id=3,left_team=1)
    result=import_openwhispr_notes(path)
    assert len(result['imported'])==1 and result['excluded']==2
    connection.close()


def test_epoch_times_equal_timestamps_and_missing_times_preserve_every_segment():
    raw=json.dumps([{'text':'a','timestamp':1_790_000_000_000},
        {'text':'b','timestamp':1_790_000_000_000},
        {'text':'c','timestamp':1_790_000_002_500}, {'text':'d'}])
    rows,untimed,origin=transcript_rows(raw)
    assert [r[2] for r in rows]==[0,0,2.5,0]
    assert len({r[0] for r in rows})==4
    assert untimed==[4] and origin==1_790_000_000_000


@pytest.mark.parametrize('text',['A legacy plain transcript.','[{broken JSON','{"unexpected":"format"}'])
def test_unknown_transcript_formats_are_kept_verbatim(text):
    rows,untimed,_=transcript_rows(text)
    assert rows[0][-1]==text and untimed==[1]


def test_transcript_only_note_can_open_search_and_filter_without_audio(tmp_path,monkeypatch):
    from PyQt6.QtWidgets import QApplication
    from ui.dashboard import DashboardWindow
    path,connection=database(tmp_path)
    insert(connection,transcript='A phrase with no timestamp.')
    import_openwhispr_notes(path)
    monkeypatch.setattr('classroom.ui.ClassroomRecorder',lambda *a,**k:pytest.fail('Import must not record'))
    app=QApplication.instance() or QApplication([])
    window=DashboardWindow(preview=True)
    assert window.stack.currentIndex()==window.PAGES.index('Classroom')
    window.note_search.setText('no timestamp')
    assert window.note_list.count()==1
    window.open_note_item(window.note_list.item(0))
    assert 'Time not supplied' in window.classroom.transcript.toPlainText()
    assert not window.classroom.retry_button.isEnabled()
    assert window.folder_filter.findData('Physics')>=0
    window.folder_filter.setCurrentIndex(window.folder_filter.findData('Physics'))
    assert window.note_list.count()==1
    window.clear_note_filters()
    assert window.folder_filter.currentData()==''
    window.close()
    connection.close()


def test_unsupported_database_does_not_create_destination(tmp_path):
    path=tmp_path/'other.db'
    sqlite3.connect(path).close()
    with pytest.raises(ValueError):import_openwhispr_notes(path)
    assert not data_root().exists()


def test_same_time_segments_all_survive_in_the_saved_database(tmp_path):
    path,connection=database(tmp_path)
    insert(connection,transcript=json.dumps([{'text':'first','timestamp':1000,'source':'mic'},
        {'text':'second','timestamp':1000,'source':'mic'},{'text':'third','timestamp':1000,'source':'system'}]))
    result=import_openwhispr_notes(path)
    assert not result['errors']
    session=Session(result['imported'][0])
    assert [r['text'] for r in session.rows()]==['first','second','third']
    connection.close()
