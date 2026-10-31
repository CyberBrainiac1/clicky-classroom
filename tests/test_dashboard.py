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
