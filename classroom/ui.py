"""Native Qt Classroom window. Opening it never opens an audio device."""
import os
import sys
from PyQt6.QtCore import QThread, QTimer, pyqtSignal, QObject
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLabel, QLineEdit, QComboBox, QCheckBox, QSpinBox, QPushButton, QGroupBox,
    QTabWidget, QPlainTextEdit, QFileDialog, QMessageBox)
from .settings import Settings, data_root
from .session import Session
from .recorder import ClassroomRecorder, import_audio, retry_session
from .notes import LocalNotes
from .engines import prepare_whisper_download


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
        layout = QVBoxLayout(self)
        self.intro = QWidget()
        intro_layout = QVBoxLayout(self.intro)
        intro_layout.setContentsMargins(0,0,0,0)
        intro_layout.addWidget(QLabel('Record a class, keep a timestamped transcript, and make study notes on this laptop.'))
        intro_layout.addWidget(QLabel('Recording starts only when you click Start. Follow your class recording rules.'))
        layout.addWidget(self.intro)
        form = QFormLayout()
        self.title = QLineEdit('Class notes')
        form.addRow('Class / topic', self.title)
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
        layout.addWidget(self.basics)
        self.settings_toggle = QPushButton('Local models & advanced settings')
        self.settings_toggle.setCheckable(True)
        layout.addWidget(self.settings_toggle)
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
        form.addRow('Speech language (blank = auto)', self.language)
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
        layout.addWidget(group)
        group.hide()
        self.settings_toggle.toggled.connect(group.setVisible)
        buttons = QHBoxLayout()
        self.start_button = QPushButton('Start class recording')
        self.start_button.setObjectName('primary')
        self.start_button.clicked.connect(self._start)
        self.stop_button = QPushButton('Stop and process')
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self._stop)
        self.import_button = QPushButton('Import saved audio…')
        self.import_button.clicked.connect(self._import)
        self.open_button = QPushButton('Open saved class…')
        self.open_button.clicked.connect(self._open)
        for button in [self.start_button, self.stop_button, self.import_button, self.open_button]:
            buttons.addWidget(button)
        layout.addLayout(buttons)
        tools = QHBoxLayout()
        self.retry_button = QPushButton('Retry transcription')
        self.retry_button.clicked.connect(self._retry)
        self.notes_button = QPushButton('Generate study notes')
        self.notes_button.clicked.connect(self._notes)
        self.prepare_button = QPushButton('Prepare offline Whisper…')
        self.prepare_button.clicked.connect(self._prepare)
        self.folder_button = QPushButton('Open class folder')
        self.folder_button.clicked.connect(self._folder)
        for button in [self.retry_button, self.notes_button, self.prepare_button, self.folder_button]:
            tools.addWidget(button)
        layout.addLayout(tools)
        self.status = QLabel('Ready. No audio device is open.')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.tabs = QTabWidget()
        self.transcript, self.notes, self.log = QPlainTextEdit(), QPlainTextEdit(), QPlainTextEdit()
        for name, edit in [('Transcript', self.transcript), ('Study notes', self.notes), ('Activity', self.log)]:
            edit.setReadOnly(True)
            self.tabs.addTab(edit, name)
        layout.addWidget(self.tabs, 1)
        try:
            self._load(Settings.load())
        except Exception as exc:
            self._message('Saved settings could not be read: '+str(exc))
        self.timer = QTimer(self)
        self.timer.timeout.connect(self._refresh)
        self.timer.start(1000)
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
        try:
            settings = self.current_settings()
            settings.save()
            self.recorder = ClassroomRecorder(settings, self.messages.status.emit)
            self.recorder.start(self.title.text().strip())
            self.session = self.recorder.session
            self._refresh()
        except Exception as exc:
            self._message('Could not start: '+str(exc))

    def _stop(self):
        if self.recorder:
            self._message('Stopping capture and saving remaining audio…')
            self._job(lambda: self.recorder.stop(), lambda path: self._message('Audio saved. Transcription/notes may still be processing.'))

    def _open(self):
        path = QFileDialog.getExistingDirectory(self, 'Open a saved class folder', str(data_root()/'sessions'))
        if path:
            try:
                self.session = Session(path)
                self._refresh()
            except Exception as exc:
                self._message('Could not open class: '+str(exc))

    def _import(self):
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
            self._set_session(session)
            self._retry()
        self._job(work, imported)

    def _set_session(self, session):
        self.session = session
        self._message('Class ready: '+str(session.path))
        self._refresh()

    def _retry(self):
        if self.session:
            try:
                settings = self.current_settings()
            except Exception as exc:
                self._message(str(exc))
                return
            session = self.session
            self._job(lambda: retry_session(session, self.messages.status.emit, settings=settings), lambda _: self._message('Class reprocessed.'))

    def _notes(self):
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
        choice = QMessageBox.question(self, 'Download local speech model?',
            f'Download/cache the Whisper model “{model}” for offline transcription? No recording will start.')
        if choice == QMessageBox.StandardButton.Yes:
            self._job(lambda: prepare_whisper_download(model), lambda path: self._message('Offline speech model ready: '+str(path)))

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
        self.start_button.setEnabled(not self.busy)
        self.stop_button.setEnabled((recording or closing_audio) and not self.jobs)
        for button in [self.import_button, self.open_button, self.prepare_button]:
            button.setEnabled(not self.busy)
        self.retry_button.setEnabled(self.session is not None and not self.busy)
        self.notes_button.setEnabled(self.session is not None and not self.busy)
        self.folder_button.setEnabled(self.session is not None)
        if self.session:
            for name, widget in [('transcript.md', self.transcript), ('notes.md', self.notes)]:
                path = self.session.path/name
                if path.exists():
                    try:
                        text = path.read_text('utf-8')
                        if widget.toPlainText() != text:
                            widget.setPlainText(text)
                    except OSError:
                        pass

    def closeEvent(self, event):
        if self.busy:
            self.showMinimized()
            self._message('Classroom is still active. Use Stop and wait for processing before exiting.')
            event.ignore()
        else:
            event.accept()

    def shutdown(self):
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
