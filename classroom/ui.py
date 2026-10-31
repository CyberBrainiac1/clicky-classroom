"""Native Qt Classroom window. Opening it never opens an audio device."""
import os
import sys
import html
import time
import sqlite3
from datetime import datetime
from PyQt6.QtCore import QThread, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox, QPushButton, QGroupBox,
    QTabWidget, QPlainTextEdit, QTextBrowser, QFileDialog, QMessageBox, QDialog,
    QScrollArea, QFrame, QMenu)
from .settings import Settings, data_root, atomic_text
from .session import Session, stamp
from .recorder import ClassroomRecorder, import_audio, retry_session
from .notes import LocalNotes
from .engines import prepare_whisper_download
from .models import prepare_parakeet_download


class Messages(QObject):
    status = pyqtSignal(str)


class Job(QThread):
    success = pyqtSignal(object)
    failed = pyqtSignal(str)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self.function = function

    def run(self):
        try:
            self.success.emit(self.function())
        except Exception as exc:
            self.failed.emit(str(exc))


class ClassroomWindow(QWidget):
    session_changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        from ui.typography import ensure_native_font
        self.setFont(ensure_native_font())
        from ui.dashboard import STYLE
        self.setObjectName('dashboard')
        self.setStyleSheet(STYLE)
        self.setWindowTitle('Clicky Classroom — local class notes')
        self.resize(940, 900)
        self.recorder, self.session = None, None
        self.jobs = set()
        self.messages = Messages(self)
        self.messages.status.connect(self._message)
        from ui.dashboard_icons import icon
        self._transcript_cache = None
        self._recording_began = None
        self._loaded_notes = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0,0,0,0)
        layout.setSpacing(0)
        # Kept for the standalone entry point; the dashboard supplies its own chrome.
        self.intro = QLabel('Clicky / Notes')
        self.intro.setObjectName('secondary')
        self.intro.setContentsMargins(32,16,32,0)
        layout.addWidget(self.intro)
        body = QWidget()
        content = QVBoxLayout(body)
        content.setContentsMargins(40,32,40,24)
        content.setSpacing(20)
        self.title = QLineEdit('Untitled note')
        self.title.setObjectName('noteTitle')
        self.title.setAccessibleName('Note title')
        content.addWidget(self.title)
        metadata = QHBoxLayout()
        metadata.setSpacing(8)
        self.date_label = QLabel(datetime.now().strftime('%b %d'))
        self.date_label.setObjectName('pill')
        self.storage_label = QLabel('Private · saved on this laptop')
        self.storage_label.setObjectName('pill')
        metadata.addWidget(self.date_label)
        metadata.addWidget(self.storage_label)
        metadata.addStretch()
        content.addLayout(metadata)
        # Options are a separate, scrollable native dialog, never a capture trigger.
        self.options_dialog = QDialog(self)
        self.options_dialog.setWindowTitle('Recording & local models')
        self.options_dialog.resize(760,720)
        self.options_dialog.setStyleSheet(STYLE)
        options_root = QVBoxLayout(self.options_dialog)
        options_scroll = QScrollArea()
        options_scroll.setWidgetResizable(True)
        options_widget = QWidget()
        options = QVBoxLayout(options_widget)
        options.setSpacing(16)
        form = QFormLayout()
        self.source = QComboBox()
        for label, value in [('Teacher in the room — microphone', 'microphone'),
                             ('Online class — computer audio', 'system'), ('Microphone + computer audio', 'both')]:
            self.source.addItem(label, value)
        form.addRow('Audio to record', self.source)
        self.device = QComboBox()
        self.device.addItem('Windows default microphone', None)
        microphone_row = QHBoxLayout()
        microphone_row.addWidget(self.device)
        refresh_microphones = QPushButton('Find microphones')
        refresh_microphones.clicked.connect(self._microphones)
        microphone_row.addWidget(refresh_microphones)
        form.addRow('Microphone', microphone_row)
        self.basics = QWidget()
        self.basics.setLayout(form)
        options.addWidget(self.basics)
        form = QFormLayout()
        self.engine = QComboBox()
        self.engine.addItem('Local Whisper (CPU)', 'whisper')
        self.engine.addItem('Local Parakeet / sherpa-onnx (OpenWhispr-style)', 'parakeet')
        form.addRow('Transcription', self.engine)
        self.whisper = QLineEdit('base')
        form.addRow('Whisper model / local folder', self.whisper)
        row = QHBoxLayout()
        self.parakeet = QLineEdit()
        self.parakeet.setPlaceholderText('Folder containing encoder, decoder, joiner and tokens')
        choose = QPushButton('Browse…')
        choose.clicked.connect(self._choose_parakeet)
        row.addWidget(self.parakeet)
        row.addWidget(choose)
        form.addRow('Parakeet model folder', row)
        self.language = QLineEdit('en')
        form.addRow('Whisper language (blank = auto)', self.language)
        self.threads = QSpinBox()
        self.threads.setRange(1, 4)
        self.threads.setValue(2)
        form.addRow('CPU threads', self.threads)
        self.live = QCheckBox('Transcribe while recording (uses more CPU/RAM)')
        form.addRow(self.live)
        self.backend = QComboBox()
        self.backend.addItem('Ollama — local only', 'ollama')
        self.backend.addItem('Local llama.cpp / LM Studio server', 'openai-local')
        form.addRow('Notes engine', self.backend)
        self.url = QLineEdit('http://127.0.0.1:11434')
        form.addRow('Local notes server', self.url)
        self.model = QLineEdit('qwen3.5:4b')
        form.addRow('Already-downloaded notes model', self.model)
        self.auto_notes = QCheckBox('Make study notes after transcription finishes')
        self.auto_notes.setChecked(True)
        form.addRow(self.auto_notes)
        group = QGroupBox('Class recording settings')
        self.settings_group = group
        group.setLayout(form)
        options.addWidget(group)
        options_scroll.setWidget(options_widget)
        options_root.addWidget(options_scroll)
        close_options = QPushButton('Done')
        close_options.clicked.connect(self.options_dialog.hide)
        options_root.addWidget(close_options)
        self.settings_toggle = QPushButton('Recording settings')
        self.settings_toggle.setObjectName('quiet')
        self.settings_toggle.setIcon(icon('sliders-horizontal'))
        self.settings_toggle.clicked.connect(self.options_dialog.show)
        self.start_button = QPushButton('Start recording')
        self.start_button.setObjectName('record')
        self.start_button.setIcon(icon('mic','#75aaff'))
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton('Stop & process')
        self.stop_button.setIcon(icon('square','#75aaff'))
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        self.import_button = QPushButton('Import audio…',self)
        self.import_button.clicked.connect(self._import)
        self.open_button = QPushButton('Open saved class…',self)
        self.open_button.clicked.connect(self._open)
        self.openwhispr_button = QPushButton('Import OpenWhispr notes…',self)
        self.openwhispr_button.clicked.connect(self._import_openwhispr)
        self.retry_button = QPushButton('Retry transcription',self)
        self.retry_button.clicked.connect(self._retry)
        self.notes_button = QPushButton('Generate study notes',self)
        self.notes_button.clicked.connect(self._notes)
        self.prepare_button = QPushButton('Prepare offline speech model…',self)
        self.prepare_button.clicked.connect(self._prepare)
        self.folder_button = QPushButton('Open note folder',self)
        self.folder_button.clicked.connect(self._folder)
        self.more_button = QPushButton('More')
        self.more_button.setIcon(icon('ellipsis'))
        self.more_menu = QMenu(self)
        self.menu_actions = []
        for button in [self.import_button,self.open_button,self.openwhispr_button,self.notes_button,self.retry_button,
                       self.prepare_button,self.folder_button]:
            button.hide()
            action = self.more_menu.addAction(button.text())
            action.triggered.connect(button.click)
            self.menu_actions.append((action,button))
        self.more_button.setMenu(self.more_menu)
        controls = QHBoxLayout()
        controls.setSpacing(8)
        controls.addWidget(self.settings_toggle)
        controls.addStretch()
        controls.addWidget(self.start_button)
        controls.addWidget(self.stop_button)
        controls.addWidget(self.more_button)
        content.addLayout(controls)
        self.session_info = QLabel('Ready when you are · no audio device is open')
        self.session_info.setObjectName('secondary')
        self.session_info.setWordWrap(True)
        content.addWidget(self.session_info)
        self.tabs = QTabWidget()
        self.tabs.setObjectName('noteTabs')
        self.transcript = QTextBrowser()
        self.transcript.setObjectName('transcriptReader')
        self.transcript.setOpenExternalLinks(False)
        self.transcript.setOpenLinks(False)
        self.notes = QPlainTextEdit()
        self.notes.setObjectName('noteEditor')
        self.notes.setPlaceholderText('Write your own notes here, or choose More → Generate study notes after transcription.')
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.document().setMaximumBlockCount(500)
        self.log.setObjectName('noteEditor')
        self.log.setPlaceholderText('Recording and processing updates appear here.')
        for name, edit in [('Transcript',self.transcript),('Your notes',self.notes),('Activity',self.log)]:
            self.tabs.addTab(edit,name)
        content.addWidget(self.tabs,1)
        footer = QHBoxLayout()
        self.status = QLabel('No recording started.')
        self.status.setObjectName('secondary')
        self.status.setWordWrap(True)
        footer.addWidget(self.status,1)
        self.save_notes_button = QPushButton('Save notes')
        self.save_notes_button.clicked.connect(self._save_notes)
        self.save_notes_button.setEnabled(False)
        self.save_notes_button.hide()
        self.tabs.currentChanged.connect(lambda index:self.save_notes_button.setVisible(index==1))
        self.notes.textChanged.connect(lambda:self.save_notes_button.setEnabled(self.notes.document().isModified() and not self.busy))
        footer.addWidget(self.save_notes_button)
        content.addLayout(footer)
        layout.addWidget(body,1)
        try:
            self._load(Settings.load())
        except Exception as exc:
            self._message('Saved settings could not be read: '+str(exc))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)
        self.source.currentIndexChanged.connect(self._refresh)
        self._refresh()

    def _load(self, value):
        for combo, key in [(self.source, value.source), (self.engine, value.engine), (self.backend, value.notes_backend)]:
            combo.setCurrentIndex(max(0, combo.findData(key)))
        if value.microphone_device is not None:
            self.device.addItem(f'Saved microphone ({value.microphone_device})', value.microphone_device)
            self.device.setCurrentIndex(self.device.count()-1)
        self.whisper.setText(value.whisper_model)
        self.parakeet.setText(value.parakeet_directory)
        self.language.setText(value.language)
        self.threads.setValue(value.threads)
        self.live.setChecked(value.live_transcription)
        self.url.setText(value.notes_url)
        self.model.setText(value.notes_model)
        self.auto_notes.setChecked(value.automatic_notes)

    def current_settings(self):
        settings = Settings(source=self.source.currentData(), microphone_device=self.device.currentData(),
            engine=self.engine.currentData(), whisper_model=self.whisper.text().strip(),
            parakeet_directory=self.parakeet.text().strip(), language=self.language.text().strip(),
            threads=self.threads.value(), live_transcription=self.live.isChecked(),
            notes_backend=self.backend.currentData(), notes_url=self.url.text().strip(),
            notes_model=self.model.text().strip(), automatic_notes=self.auto_notes.isChecked())
        settings.validate()
        return settings

    def _message(self, text):
        self.status.setText(text)
        self.log.appendPlainText(text)

    def _job(self, function, done=lambda result: None):
        job = Job(function, self)
        self.jobs.add(job)
        job.success.connect(done)
        job.failed.connect(lambda text: self._message('Error: '+text))
        job.finished.connect(lambda: self._job_finished(job))
        job.start()
        self._refresh()

    def _job_finished(self, job):
        self.jobs.discard(job)
        job.deleteLater()
        self._refresh()
        self.session_changed.emit()

    def _choose_parakeet(self):
        path = QFileDialog.getExistingDirectory(self, 'Select local Parakeet model folder')
        if path:
            self.parakeet.setText(path)

    def _microphones(self):
        try:
            import sounddevice as sd
            selected = self.device.currentData()
            self.device.clear()
            self.device.addItem('Windows default microphone', None)
            for index, device in enumerate(sd.query_devices()):
                if device['max_input_channels']:
                    self.device.addItem(device['name'], index)
            self.device.setCurrentIndex(max(0, self.device.findData(selected)))
        except Exception as exc:
            self._message('Could not list microphones: '+str(exc))

    def _start(self):
        if not self._can_leave():
            return
        try:
            settings = self.current_settings()
            settings.save()
            self.recorder = ClassroomRecorder(settings, self.messages.status.emit)
            self.recorder.start(self.title.text().strip())
            self._set_session(self.recorder.session, starting=True)
            self._recording_began = time.monotonic()
            self._refresh()
        except Exception as exc:
            self._message('Could not start: '+str(exc))

    def _stop(self):
        if self.recorder:
            self._message('Stopping capture and saving remaining audio…')
            self._job(lambda: self.recorder.stop(), lambda path: self._message('Audio saved. Transcription/notes may still be processing.'))

    def _open(self):
        if not self._can_leave():
            return
        path = QFileDialog.getExistingDirectory(self, 'Open a saved class folder', str(data_root()/'sessions'))
        if path:
            try:
                self._set_session(Session(path))
            except Exception as exc:
                self._message('Could not open class: '+str(exc))

    def _import(self):
        if not self._can_leave():
            return
        path, _ = QFileDialog.getOpenFileName(self, 'Import class audio', '', 'Audio (*.wav *.flac *.ogg *.aiff);;All files (*)')
        if not path:
            return
        try:
            settings = self.current_settings()
            settings.save()
        except Exception as exc:
            self._message(str(exc))
            return
        title = self.title.text()
        def work():
            return import_audio(path, title, settings)
        self._message('Importing the selected audio file…')
        def imported(session):
            # The completed import is still registered until QThread.finished.
            # Its result belongs to this job, rather than a user switching notes.
            self._set_session(session, starting=True)
            self._retry()
        self._job(work, imported)

    def _import_openwhispr(self):
        if not self._can_leave():
            return
        from .openwhispr_import import default_database, import_openwhispr_notes
        database=default_database()
        if not database.is_file():
            path,_=QFileDialog.getOpenFileName(self,'Select OpenWhispr notes database','','SQLite database (*.db)')
            if not path:
                return
            database=path
        self._message('Copying local OpenWhispr notes. Originals will stay in OpenWhispr.')
        def imported(result):
            self.session_changed.emit()
            if result['imported']:
                self._set_session(Session(result['imported'][0]),starting=True)
            message=f"Imported {len(result['imported'])} notes; {result['alreadyImported']} already present; {result['excluded']} deleted/unavailable notes excluded."
            if result['changedSourceKept']:
                message+=f" {result['changedSourceKept']} source notes changed; existing Clicky copies were kept."
            if result['errors']:
                message+=f" {len(result['errors'])} could not be imported: "+result['errors'][0]['error']
            self._message(message)
        self._job(lambda:import_openwhispr_notes(database),imported)

    def _can_leave(self):
        if self.busy:
            self._message('Finish the active recording or processing before opening another note.')
            return False
        if self.notes.document().isModified():
            self._message('Save your edited notes before opening another note.')
            return False
        return True

    def new_draft(self):
        if not self._can_leave():
            return False
        self.session = self.recorder = None
        self.title.setReadOnly(False)
        self.title.setText('Untitled note')
        self.date_label.setText(datetime.now().strftime('%b %d'))
        self.notes.clear()
        self.notes.document().setModified(False)
        self.log.clear()
        self._transcript_cache = self._loaded_notes = None
        self._recording_began = None
        self._message('New note. Choose Start recording or write your own notes.')
        self._refresh()
        self.session_changed.emit()
        return True

    def _set_session(self, session, starting=False):
        if not starting and self.session and self.session.path == session.path:
            return True
        if not starting and not self._can_leave():
            return False
        self.session = session
        self._transcript_cache = self._loaded_notes = None
        self.title.setText(session.metadata.get('title','Untitled note'))
        self.title.setReadOnly(True)
        created = session.metadata.get('created','')
        try:
            self.date_label.setText(datetime.fromisoformat(created).strftime('%b %d'))
        except ValueError:
            self.date_label.setText('Saved note')
        self.notes.clear()
        self.notes.document().setModified(False)
        self.tabs.setCurrentIndex(0)
        self._message('Class ready: '+str(session.path))
        self._refresh()
        self.session_changed.emit()
        return True

    def _save_notes(self):
        if self.busy:
            self._message('Wait for processing to finish before saving edited notes.')
            return
        try:
            if self.session is None:
                session = Session.create(self.title.text().strip(),self.current_settings())
                session.set_status('notes-only')
                self.session = session
                self.title.setReadOnly(True)
            text = self.notes.toPlainText()
            atomic_text(self.session.path/'notes.md',text)
            self._loaded_notes = text
            self.notes.document().setModified(False)
            self._message('Your notes are saved on this laptop.')
            self._refresh()
            self.session_changed.emit()
        except Exception as exc:
            self._message('Could not save notes: '+str(exc))

    def _retry(self):
        if self.notes.document().isModified():
            self._message('Save edited notes before retrying transcription.')
            return
        if self.session:
            try:
                settings = self.current_settings()
            except Exception as exc:
                self._message(str(exc))
                return
            session = self.session
            self._job(lambda: retry_session(session, self.messages.status.emit, settings=settings), lambda _: self._message('Class reprocessed.'))

    def _notes(self):
        if self.notes.document().isModified():
            self._message('Save edited notes before generating study notes.')
            return
        if self.session:
            try:
                settings = self.current_settings()
            except Exception as exc:
                self._message(str(exc))
                return
            session = self.session
            self._job(lambda: LocalNotes(settings).generate(session, self.messages.status.emit),
                      lambda path: self._message('Study notes saved: '+str(path)))

    def _prepare(self):
        model = self.whisper.text().strip()
        parakeet = self.engine.currentData() == 'parakeet'
        choice = QMessageBox.question(self, 'Download local speech model?',
            'Prepare Parakeet TDT0.6Bv3 in Clicky’s own cache? If missing, about680MB will be downloaded. No recording will start.' if parakeet else
            f'Download/cache the Whisper model “{model}” for offline transcription? No recording will start.')
        if choice == QMessageBox.StandardButton.Yes:
            def ready(path):
                if parakeet:
                    self.parakeet.setText(str(path))
                self._message('Offline speech model ready: '+str(path))
            self._job(prepare_parakeet_download if parakeet else lambda: prepare_whisper_download(model), ready)

    def _folder(self):
        if self.session and os.name == 'nt':
            os.startfile(self.session.path)

    @property
    def busy(self):
        if self.jobs:
            return True
        if self.recorder:
            workers = self.recorder.capture_threads+[self.recorder.writer_thread, self.recorder.asr_thread]
            return any(worker and worker.is_alive() for worker in workers)
        return False

    def _refresh(self):
        recording = bool(self.recorder and self.recorder.recording)
        closing_audio = bool(self.recorder and any(worker and worker.is_alive()
            for worker in self.recorder.capture_threads+[self.recorder.writer_thread]))
        self.settings_group.setEnabled(not recording)
        self.basics.setEnabled(not recording)
        dirty = self.notes.document().isModified()
        self.start_button.setEnabled(not self.busy and not dirty)
        self.stop_button.setEnabled((recording or closing_audio) and not self.jobs)
        self.stop_button.setVisible(recording or closing_audio)
        self.start_button.setVisible(not recording and not closing_audio)
        for button in [self.import_button, self.open_button, self.openwhispr_button, self.prepare_button]:
            button.setEnabled(not self.busy)
        has_audio=bool(self.session and any(self.session.path.glob('audio-*.wav')))
        self.retry_button.setEnabled(has_audio and not self.busy and not dirty)
        self.retry_button.setToolTip('Requires saved audio. Imported OpenWhispr notes keep their existing transcript without copying audio.')
        self.notes_button.setEnabled(self.session is not None and not self.busy and not dirty)
        self.folder_button.setEnabled(self.session is not None)
        self.notes.setReadOnly(self.busy)
        self.save_notes_button.setEnabled(dirty and not self.busy)
        for action,button in self.menu_actions:
            action.setEnabled(button.isEnabled())
        if recording:
            elapsed = time.monotonic()-(self._recording_began or time.monotonic())
            mode = 'Live transcription' if self.recorder.settings.live_transcription else 'Transcription after stopping'
            self.session_info.setText('Recording · '+stamp(elapsed)+' · '+mode)
        elif self.busy:
            self.session_info.setText('Processing · your saved audio stays on this laptop')
        elif self.session:
            self.session_info.setText('Imported from OpenWhispr · audio not copied' if self.session.metadata.get('origin',{}).get('app')=='OpenWhispr' else 'Saved note · '+self.session.metadata.get('status','saved').replace('-',' '))
        else:
            source_name={'microphone':'Microphone','system':'Computer audio','both':'Microphone + computer audio'}.get(self.source.currentData(),'Audio')
            self.session_info.setText('Ready · '+source_name+' · no audio device is open')
        if self.session:
            try:
                rows = self.session.rows()
                untimed=set(self.session.metadata.get('untimed_chunk_ids',[]))
                for row in rows:
                    row['timestamp_unknown']=row['id'] in untimed
                signature = [(r['id'],r['status'],r['text'],r['error']) for r in rows]
                if signature != self._transcript_cache:
                    scroll = self.transcript.verticalScrollBar()
                    position, follow_end = scroll.value(), scroll.value() >= scroll.maximum()-16
                    self.transcript.setHtml(self._transcript_html(rows))
                    scroll.setValue(scroll.maximum() if follow_end else position)
                    self._transcript_cache = signature
                path = self.session.path/'notes.md'
                if path.exists() and not dirty:
                    text = path.read_text('utf-8')
                    if text != self._loaded_notes:
                        self.notes.setPlainText(text)
                        self.notes.document().setModified(False)
                        self._loaded_notes = text
            except (OSError,ValueError,sqlite3.Error) as exc:
                self._message('Could not refresh saved note: '+str(exc))
        elif self._transcript_cache != 'empty':
            self.transcript.setHtml(self._transcript_html([]))
            self._transcript_cache = 'empty'

    @staticmethod
    def _transcript_html(rows):
        rendered = []
        for row in rows:
            if row['status'] == 'silence':
                continue
            text = row['text'] if row['status'] == 'done' else ('Transcription pending' if row['status'] == 'pending' else 'Transcription failed: '+row['error'])
            if not text:
                continue
            source = {'microphone':'Microphone','system':'Computer audio','import':'Imported audio'}.get(row['source'],'Audio')
            rendered.append('<p style="color:#90979f;font-size:11px;margin-top:20px;margin-bottom:8px">'+
                ('Time not supplied' if row.get('timestamp_unknown') else stamp(row['start_seconds']))+' &nbsp; '+source+'</p><table width="100%" cellspacing="0" cellpadding="14" bgcolor="#24272a"><tr><td>'+html.escape(text).replace('\n','<br>')+'</td></tr></table>')
        if not rendered:
            return '<div style="color:#90979f;margin-top:90px"><p style="font-size:22px;color:#d6d9de">Your transcript starts here</p><p>Record a class or import audio to keep the conversation in one place.</p><p>You can also write a note in the Your notes tab.</p></div>'
        return '<html><body style="font-family:Segoe UI;font-size:15px;color:#e3e5e8">'+''.join(rendered)+'</body></html>'

    def closeEvent(self, event):
        if self.notes.document().isModified():
            self._save_notes()
            if self.notes.document().isModified():
                event.ignore()
                return
        if self.busy:
            self.showMinimized()
            self._message('Classroom is still active. Use Stop and wait for processing before exiting.')
            event.ignore()
        else:
            event.accept()

    def shutdown(self):
        if self.notes.document().isModified() and not self.busy:
            self._save_notes()
        if self.recorder:
            self.recorder.stop()
            self.recorder.wait_processing(timeout=2)


def run():
    app = QApplication.instance() or QApplication(sys.argv)
    from ui.design import apply_theme
    apply_theme(app)
    window = ClassroomWindow()
    app.aboutToQuit.connect(window.shutdown)
    window.show()
    return app.exec()


if __name__ == '__main__':
    sys.exit(run())
