import json
from pathlib import Path
import pytest


@pytest.fixture
def app(monkeypatch, tmp_path):
    monkeypatch.setenv('QT_QPA_PLATFORM','offscreen')
    monkeypatch.setenv('CLICKY_CLASSROOM_DATA_DIR', str(tmp_path/'classes'))
    from PyQt6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


def test_navigation_and_classroom_are_additions_without_capture(app, monkeypatch):
    from ui.dashboard import DashboardWindow
    monkeypatch.setattr('classroom.ui.ClassroomRecorder', lambda *a,**k: pytest.fail('No capture on navigation'))
    window = DashboardWindow(preview=True)
    window.show()
    for page in window.PAGES:
        window.select_page(page)
        app.processEvents()
        assert window.stack.currentIndex() == window.PAGES.index(page)
    assert window.classroom.recorder is None
    assert not window.send_button.isEnabled()
    window.close()


def test_regular_assistant_routes_and_streamed_reply(app):
    from ui.dashboard import DashboardWindow
    sent = []
    window = DashboardWindow(actions={'submit_text':sent.append, 'assistant':lambda:sent.append('floating')},
        snapshot=lambda:{'state':'Idle','models':{'llm':'local model','stt':'Whisper','tts':'Windows'}})
    window.question.setText('Explain this graph')
    window.send_question()
    assert sent == ['Explain this graph']
    window.append_response('The slope ')
    window.append_response('represents velocity.')
    assert 'The slope represents velocity.' in window.conversation.toPlainText()
    window.dispatch('assistant')
    assert sent[-1] == 'floating'
    assert 'local model' in window.models.text()
    window.close()


def test_errors_and_stale_status_remain_visible(app):
    from ui.dashboard import DashboardWindow
    def broken(): raise RuntimeError('App state unavailable')
    window = DashboardWindow(snapshot=broken)
    assert 'unavailable' in window.freshness.text().lower()
    assert 'App state unavailable' in window.notice.text()
    assert not window.notice.isHidden()
    window.record_activity('Transcription paused: model missing',error=True)
    assert 'model missing' in window.activity.toPlainText()
    window.close()


def test_saved_class_library_opens_actual_classroom_session(app):
    from classroom.settings import Settings
    from classroom.session import Session
    from ui.dashboard import DashboardWindow
    session = Session.create('Physics review', Settings())
    window = DashboardWindow(preview=True)
    assert window.library.rowCount() == 1
    assert window.library.item(0,0).text() == 'Physics review'
    window.library.selectRow(0)
    window.open_selected_class()
    assert window.classroom.session.path == session.path
    assert window.stack.currentIndex() == window.PAGES.index('Classroom')
    assert window.classroom.recorder is None
    window.close()


def test_note_search_reads_transcripts_and_opens_filtered_result(app):
    from classroom.settings import Settings
    from classroom.session import Session, RATE
    from ui.dashboard import DashboardWindow
    first = Session.create('Physics',Settings())
    first.add_chunk('import',0,RATE)
    first.finish_chunk(first.pending()['id'],'Conservation of momentum')
    Session.create('Precalculus',Settings())
    window = DashboardWindow(preview=True)
    window.note_search.setText('MOMENTUM')
    assert window.note_list.count() == 1
    window.open_note_item(window.note_list.item(0))
    assert window.classroom.session.path == first.path
    assert 'Conservation of momentum' in window.classroom.transcript.toPlainText()
    window.note_search.setText('no match')
    assert window.note_list.count() == 0
    assert window.note_list_empty.text() == 'No matching notes.'
    window.close()


def test_note_switch_preserves_unsaved_edits_and_saved_notes_survive_reopen(app):
    from classroom.settings import Settings
    from classroom.session import Session
    from ui.dashboard import DashboardWindow
    first = Session.create('First',Settings())
    second = Session.create('Second',Settings())
    window = DashboardWindow(preview=True)
    window.select_page('Classroom')
    window.classroom._set_session(first)
    window.classroom.notes.insertPlainText('My own derivation')
    assert window.classroom.notes.document().isModified()
    assert not window.classroom._set_session(second)
    assert window.classroom.session.path == first.path
    window.classroom._refresh()
    assert window.classroom.notes.toPlainText() == 'My own derivation'
    window.classroom._save_notes()
    assert (first.path/'notes.md').read_text('utf-8') == 'My own derivation'
    window.note_search.setText('derivation')
    assert window.note_list.count() == 1
    assert window.classroom._set_session(second)
    assert window.classroom.notes.toPlainText() == ''
    assert window.classroom._set_session(first)
    assert window.classroom.notes.toPlainText() == 'My own derivation'
    assert not window.classroom.notes.document().isModified()
    window.close()


def test_new_text_note_saves_without_recording_and_close_preserves_edits(app,monkeypatch):
    from ui.dashboard import DashboardWindow
    monkeypatch.setattr('classroom.ui.ClassroomRecorder',lambda *a,**k:pytest.fail('No capture for text notes'))
    window = DashboardWindow(preview=True)
    window.new_note()
    window.classroom.title.setText('My homework')
    window.classroom.notes.insertPlainText('Check the signs in the friction equation.')
    window.close()
    session = window.classroom.session
    assert session.metadata['status'] == 'notes-only'
    assert (session.path/'notes.md').read_text('utf-8').startswith('Check the signs')
    assert not list(session.path.glob('*.wav'))
    assert window.classroom.recorder is None


def test_completed_file_import_can_install_its_session_before_worker_finished(app,monkeypatch):
    import time
    from classroom.settings import Settings
    from classroom.session import Session
    from ui.dashboard import DashboardWindow
    imported = Session.create('Imported physics',Settings())
    monkeypatch.setattr('classroom.ui.QFileDialog.getOpenFileName',lambda *a,**k:('fixture.wav',''))
    monkeypatch.setattr('classroom.ui.import_audio',lambda *a,**k:imported)
    monkeypatch.setattr('classroom.settings.Settings.save',lambda self:None)
    window = DashboardWindow(preview=True)
    window.select_page('Classroom')
    retries=[]
    monkeypatch.setattr(window.classroom,'_retry',lambda:retries.append(window.classroom.session.path))
    window.classroom._import()
    deadline=time.monotonic()+3
    while window.classroom.jobs and time.monotonic()<deadline:
        app.processEvents()
        time.sleep(.01)
    assert not window.classroom.jobs
    assert window.classroom.session.path == imported.path
    assert retries == [imported.path]
    assert window.classroom.recorder is None
    window.close()


def test_transcript_content_is_text_and_busy_class_cannot_be_replaced(app):
    from classroom.settings import Settings
    from classroom.session import Session,RATE
    from ui.dashboard import DashboardWindow
    first = Session.create('First',Settings())
    second = Session.create('Second',Settings())
    first.add_chunk('import',0,RATE)
    first.finish_chunk(first.pending()['id'],'<script>do not execute</script> & x < 2')
    window = DashboardWindow(preview=True)
    window.select_page('Classroom')
    window.classroom._set_session(first)
    assert '<script>do not execute</script> & x < 2' in window.classroom.transcript.toPlainText()
    window.classroom.jobs.add('active processing')
    assert not window.classroom._set_session(second)
    assert not window.classroom.new_draft()
    assert window.classroom.session.path == first.path
    window.classroom.jobs.clear()
    window.close()


@pytest.mark.parametrize('size',[(1000,700),(1180,820),(1440,900)])
def test_dashboard_native_render_sizes(app, size, tmp_path):
    from ui.dashboard import DashboardWindow
    window = DashboardWindow(preview=True)
    window.resize(*size)
    window.show()
    app.processEvents()
    image = window.grab()
    assert not image.isNull()
    assert window.width() == size[0]
    assert window.height() == size[1]
    assert window.activity.width() <= window.width()-192
    assert image.save(str(tmp_path/f'dashboard-{size[0]}.png'))
    window.close()
