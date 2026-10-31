"""Clicky's additive native control dashboard, using existing app callbacks."""
from datetime import datetime
import json
from pathlib import Path
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QListWidget, QStackedWidget,
    QPlainTextEdit, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea)

from classroom.settings import data_root
from classroom.session import Session

STYLE = '''
QWidget#dashboard { background:#121216; color:#f0f0f5; }
QWidget { font-family:"Segoe UI"; font-size:13px; color:#f0f0f5; }
QFrame#sidebar { background:#17171d; border-right:1px solid #30303b; }
QLabel#brand { font-size:20px; font-weight:600; }
QLabel#pageTitle { font-size:24px; font-weight:600; }
QLabel#sectionTitle { font-size:15px; font-weight:600; }
QLabel#secondary { color:#a0a0b3; }
QLabel#value { font-size:20px; font-weight:600; }
QLabel#notice { background:#30271b; color:#f1ce95; padding:12px; border-radius:4px; }
QFrame#surface { background:#1c1c22; border:1px solid #30303b; border-radius:6px; }
QPushButton { background:#24242e; border:1px solid #3c3c4b; border-radius:4px; padding:8px 16px; min-height:20px; }
QPushButton:hover { background:#30303c; border-color:#67677d; }
QPushButton:focus { border:1px solid #65a5ff; }
QPushButton:disabled { color:#81818e; border-color:#30303b; background:#1c1c22; }
QPushButton#primary { background:#0078ff; color:white; border-color:#0078ff; }
QPushButton#primary:hover { background:#218aff; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget::item { height:40px; padding-left:12px; color:#b8b8c8; border-radius:4px; }
QListWidget::item:selected { background:#192b43; color:#f0f0f5; border-left:3px solid #0078ff; }
QListWidget::item:hover:!selected { background:#23232c; }
QPlainTextEdit, QLineEdit, QTableWidget, QComboBox, QSpinBox { background:#1c1c22; color:#f0f0f5; border:1px solid #3c3c4b; border-radius:4px; padding:8px; }
QPlainTextEdit:focus, QLineEdit:focus { border-color:#65a5ff; }
QTableWidget { gridline-color:#30303b; selection-background-color:#192b43; }
QHeaderView::section { background:#24242e; color:#a0a0b3; border:0; padding:10px; text-align:left; }
QScrollArea { background:transparent; border:0; }
QScrollBar:vertical { background:#17171d; width:10px; }
QScrollBar::handle:vertical { background:#4a4a5b; min-height:24px; border-radius:4px; }
QGroupBox { border:1px solid #30303b; border-radius:6px; margin-top:16px; padding:16px; }
QGroupBox::title { subcontrol-origin:margin; left:16px; color:#a0a0b3; }
QTabWidget::pane { border:1px solid #30303b; }
QTabBar::tab { background:#24242e; padding:10px 16px; }
QTabBar::tab:selected { background:#192b43; }
'''


def label(text, name='secondary'):
    widget = QLabel(text)
    widget.setObjectName(name)
    widget.setWordWrap(True)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    return widget


def page(title, subtitle):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(24,24,24,24)
    layout.setSpacing(24)
    heading = QVBoxLayout()
    heading.setSpacing(8)
    heading.addWidget(label(title,'pageTitle'))
    heading.addWidget(label(subtitle))
    layout.addLayout(heading)
    return widget, layout


class DashboardWindow(QWidget):
    PAGES = ['Overview','Assistant','Classroom','Class library','Tools','Settings']

    def __init__(self, actions=None, snapshot=None, classroom_factory=None, preview=False):
        super().__init__()
        from ui.typography import ensure_native_font
        self.setFont(ensure_native_font())
        self.actions = actions or {}
        self.snapshot = snapshot
        self.classroom_factory = classroom_factory
        self.preview = preview
        self.classroom = None
        self.library_rows = []
        self._assistant_state = 'Ready'
        self._response_started = False
        self._recording = False
        self.setObjectName('dashboard')
        self.setWindowTitle('Clicky — Dashboard')
        self.resize(1180,820)
        self.setMinimumSize(1000,700)
        self.setStyleSheet(STYLE)
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(192)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16,24,16,24)
        side.setSpacing(24)
        side.addWidget(label('Clicky','brand'))
        self.navigation = QListWidget()
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.navigation.addItems(self.PAGES)
        self.navigation.setAccessibleName('Dashboard navigation')
        side.addWidget(self.navigation,1)
        self.mode = label('Preview — controls are not connected' if preview else 'Your desktop companion')
        side.addWidget(self.mode)
        self.menu_button = self.action_button('All Clicky controls','all_controls')
        side.addWidget(self.menu_button)
        root.addWidget(sidebar)
        self.stack = QStackedWidget()
        root.addWidget(self.stack,1)
        self._build_overview()
        self._build_assistant()
        self.classroom_slot, slot_layout = page('Classroom','Record teacher audio and turn the class into local notes.')
        self.classroom_slot_layout = slot_layout
        self.stack.addWidget(self.classroom_slot)
        self._build_library()
        self._build_tools()
        self._build_settings()
        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.setCurrentRow(0)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)
        self.refresh_library()
        self.refresh_status()

    def action_button(self, text, action, primary=False):
        button = QPushButton(text)
        button.setAccessibleName(text)
        button.setObjectName('primary' if primary else 'action')
        button.clicked.connect(lambda checked=False: self.dispatch(action))
        if action not in self.actions:
            button.setEnabled(False)
            button.setToolTip('Available when this dashboard is connected to the full Clicky app.')
        return button

    def dispatch(self, action):
        try:
            if action in self.actions:
                self.actions[action]()
            else:
                self.record_activity('This control is not connected in preview mode.')
        except Exception as exc:
            self.record_activity(str(exc), error=True)

    def _build_overview(self):
        widget, layout = page('Your workspace','Continue with Clicky, check a class, or open a tool.')
        self.notice = label('', 'notice')
        self.notice.hide()
        layout.addWidget(self.notice)
        status = QHBoxLayout()
        status.setSpacing(16)
        self.values = {}
        for key, title, context in [('assistant','Assistant','Live state of the regular assistant'),
                                    ('classroom','Classroom','Recording and processing status'),
                                    ('saved','Saved classes','Stored locally on this laptop')]:
            frame = QFrame()
            frame.setObjectName('surface')
            body = QVBoxLayout(frame)
            body.setContentsMargins(16,16,16,16)
            body.setSpacing(8)
            body.addWidget(label(title,'sectionTitle'))
            value = label('Not connected' if self.preview and key=='assistant' else 'Ready','value')
            self.values[key] = value
            body.addWidget(value)
            body.addWidget(label(context))
            status.addWidget(frame,1)
        layout.addLayout(status)
        columns = QHBoxLayout()
        columns.setSpacing(24)
        left = QVBoxLayout()
        left.setSpacing(12)
        left.addWidget(label('Continue working','sectionTitle'))
        ask = QPushButton('Ask Clicky')
        ask.setObjectName('primary')
        ask.clicked.connect(lambda: self.select_page('Assistant'))
        left.addWidget(ask)
        start = QPushButton('Open Classroom')
        start.clicked.connect(lambda: self.select_page('Classroom'))
        left.addWidget(start)
        left.addWidget(self.action_button('Open Sketch','sketch'))
        left.addWidget(self.action_button('Work & routines','work'))
        left.addStretch()
        right = QVBoxLayout()
        right.setSpacing(12)
        right.addWidget(label('Selected models','sectionTitle'))
        self.models = label('The full app supplies model selections. Opening this page does not test a microphone or contact a model server.')
        right.addWidget(self.models)
        right.addWidget(label('A selected provider is configuration, not a verified connection.'))
        self.freshness = label('Waiting for app state')
        right.addWidget(self.freshness)
        right.addStretch()
        columns.addLayout(left,1)
        columns.addLayout(right,1)
        layout.addLayout(columns)
        layout.addWidget(label('Recent activity','sectionTitle'))
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.document().setMaximumBlockCount(100)
        self.activity.setMaximumHeight(144)
        self.activity.setPlaceholderText('Errors and recent actions appear here. No activity yet.')
        layout.addWidget(self.activity)
        self.stack.addWidget(widget)

    def _build_assistant(self):
        widget, layout = page('Assistant','The regular Clicky assistant, with your existing screen guidance and conversation.')
        tools = QHBoxLayout()
        tools.setSpacing(8)
        tools.addWidget(self.action_button('Show floating companion','assistant'))
        tools.addWidget(self.action_button('Stop assistant','stop'))
        tools.addStretch()
        layout.addLayout(tools)
        self.conversation = QPlainTextEdit()
        self.conversation.setReadOnly(True)
        self.conversation.setPlaceholderText('Ask a question below. Responses from Clicky stream here.')
        layout.addWidget(self.conversation,1)
        entry = QHBoxLayout()
        entry.setSpacing(8)
        self.question = QLineEdit()
        self.question.setPlaceholderText('Ask about your screen, a task, or something you are learning…')
        self.question.setAccessibleName('Question for Clicky')
        self.question.returnPressed.connect(self.send_question)
        self.send_button = QPushButton('Send')
        self.send_button.setObjectName('primary')
        self.send_button.setEnabled('submit_text' in self.actions)
        self.question.setEnabled('submit_text' in self.actions)
        self.send_button.clicked.connect(self.send_question)
        entry.addWidget(self.question,1)
        entry.addWidget(self.send_button)
        layout.addLayout(entry)
        self.stack.addWidget(widget)

    def _build_library(self):
        widget, layout = page('Class library','Your saved audio, transcripts, and study notes.')
        controls = QHBoxLayout()
        refresh = QPushButton('Refresh classes')
        refresh.clicked.connect(self.refresh_library)
        controls.addWidget(refresh)
        self.open_class_button = QPushButton('Open selected class')
        self.open_class_button.clicked.connect(self.open_selected_class)
        controls.addWidget(self.open_class_button)
        controls.addStretch()
        layout.addLayout(controls)
        self.library = QTableWidget(0,5)
        self.library.setHorizontalHeaderLabels(['Class','Recorded','Status','Transcript','Notes'])
        self.library.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.library.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.library.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.library.setShowGrid(False)
        self.library.verticalHeader().hide()
        self.library.horizontalHeader().setSectionResizeMode(0,QHeaderView.ResizeMode.Stretch)
        for col in range(1,5):
            self.library.horizontalHeader().setSectionResizeMode(col,QHeaderView.ResizeMode.ResizeToContents)
        self.library.doubleClicked.connect(self.open_selected_class)
        layout.addWidget(self.library,1)
        self.library_empty = label('No saved classes yet. Open Classroom when you are ready to record or import a file.')
        layout.addWidget(self.library_empty)
        self.stack.addWidget(widget)

    def _build_tools(self):
        widget, layout = page('Tools','The same Clicky tools, collected in one place.')
        groups = [
            ('Create and work', [('Sketch & whiteboard','sketch'),('Work & routines','work'),('Connections & sharing','connections')]),
            ('Study and context', [('Open study journal','journal'),('Attach a document','attach'),('Choose AI provider / model','all_controls')]),
            ('Capture and review', [('Start lesson screen recording','lesson_start'),('Stop lesson screen recording','lesson_stop'),
                                    ('Start workflow capture','workflow_start'),('Stop + explain workflow','workflow_stop')]),
            ('Setup and repair', [('Setup wizard','setup'),('Save diagnostics','diagnostics'),('Protected API keys','api_keys')]),
        ]
        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(24)
        for index, (title, actions) in enumerate(groups):
            column = QVBoxLayout()
            column.setSpacing(12)
            column.addWidget(label(title,'sectionTitle'))
            for title_, key in actions:
                column.addWidget(self.action_button(title_,key))
            column.addStretch()
            grid.addLayout(column,index//2,index%2)
        layout.addLayout(grid)
        layout.addStretch()
        self.stack.addWidget(widget)

    def _build_settings(self):
        widget, layout = page('Settings','Use Clicky’s existing settings. Changes apply to the regular assistant too.')
        grid = QGridLayout()
        grid.setSpacing(16)
        for index, name in enumerate(['General','Voice','Microphone','Shortcuts','History','Getting started','Updates']):
            grid.addWidget(self.action_button(name,'settings:'+name),index//2,index%2)
        layout.addLayout(grid)
        layout.addWidget(self.action_button('Protected API keys','api_keys'))
        layout.addWidget(label('Classroom has separate recording and local-model settings on its own page. Existing assistant shortcuts, voice and model choices stay in Clicky’s settings.'))
        layout.addStretch()
        self.stack.addWidget(widget)

    def select_page(self, name):
        self.navigation.setCurrentRow(self.PAGES.index(name))
        return self.classroom if name == 'Classroom' else None

    def _navigate(self, row):
        if row < 0:
            return
        if self.PAGES[row] == 'Classroom' and self.classroom is None:
            from classroom.ui import ClassroomWindow
            self.classroom = self.classroom_factory() if self.classroom_factory else ClassroomWindow()
            self.classroom.intro.hide()
            self.classroom.setWindowFlags(Qt.WindowType.Widget)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(self.classroom)
            self.classroom_slot_layout.addWidget(scroll,1)
            self.classroom.messages.status.connect(self.record_activity)
        if self.PAGES[row] == 'Class library':
            self.refresh_library()
        self.stack.setCurrentIndex(row)

    def refresh_library(self):
        rows = []
        root = data_root()/'sessions'
        errors = 0
        if root.exists():
            for path in sorted(root.iterdir(),reverse=True):
                try:
                    if not path.is_dir():
                        continue
                    session = Session(path)
                    rows.append((session, [session.metadata.get('title','Untitled class'),
                        session.metadata.get('created','')[:16].replace('T',' '), session.metadata.get('status','unknown'),
                        'Saved' if (path/'transcript.md').exists() else 'Pending',
                        'Saved' if (path/'notes.md').exists() else 'Pending']))
                except (OSError, ValueError, KeyError):
                    errors += 1
        self.library_rows = rows
        self.library.setRowCount(len(rows))
        for index, (_, values) in enumerate(rows):
            for column, value in enumerate(values):
                self.library.setItem(index,column,QTableWidgetItem(str(value)))
        self.library_empty.setVisible(not rows)
        self.open_class_button.setEnabled(bool(rows))
        self.values['saved'].setText(str(len(rows)))
        if errors:
            self.record_activity(f'{errors} saved class folder(s) could not be read. Check the folder before retrying.',error=True)

    def open_selected_class(self, *args):
        row = self.library.currentRow()
        if not 0 <= row < len(self.library_rows):
            return
        self.select_page('Classroom')
        if self.classroom.busy:
            self.record_activity('Finish the active class before opening another.', error=True)
            return
        self.classroom._set_session(self.library_rows[row][0])

    def send_question(self):
        text = self.question.text().strip()
        if not text or 'submit_text' not in self.actions:
            return
        self.conversation.appendPlainText('You\n'+text+'\n')
        self.question.clear()
        self._response_started = False
        try:
            self.actions['submit_text'](text)
        except Exception as exc:
            self.record_activity(str(exc),error=True)

    def append_response(self, text):
        if not self._response_started:
            self.conversation.appendPlainText('Clicky\n')
            self._response_started = True
        self.conversation.insertPlainText(text)

    def set_assistant_state(self, value):
        self._assistant_state = getattr(value,'name',str(value)).replace('_',' ').title()
        if self._assistant_state == 'Thinking':
            self._response_started = False
        self.values['assistant'].setText(self._assistant_state)

    def set_recording_state(self, active, path=''):
        self._recording = active
        self.record_activity('Lesson screen recording started.' if active else 'Lesson screen recording stopped.')

    def record_activity(self, message, error=False):
        now = datetime.now().strftime('%H:%M:%S')
        self.activity.appendPlainText(now+'  '+str(message))
        if error:
            self.notice.setText('Needs attention · '+str(message))
            self.notice.show()

    def refresh_status(self):
        try:
            if self.snapshot is not None:
                value = self.snapshot()
                self.set_assistant_state(value.get('state',self._assistant_state))
                models = value.get('models',{})
                self.models.setText('\n'.join(f'{key.upper()}: {name}' for key,name in models.items()))
                self.freshness.setText('Updated '+datetime.now().strftime('%H:%M:%S')+' · app state')
            elif self.preview:
                self.freshness.setText('Preview · no live assistant connected')
            if self.classroom is not None:
                state = 'Recording' if self.classroom.recorder and self.classroom.recorder.recording else 'Processing' if self.classroom.busy else 'Ready'
            else:
                state = 'Not recording'
            self.values['classroom'].setText(state)
        except Exception as exc:
            self.freshness.setText('State unavailable · '+datetime.now().strftime('%H:%M:%S'))
            self.record_activity('Could not refresh app state: '+str(exc),error=True)


def preview(render=None):
    """Development preview only; no assistant, microphone, hooks or servers."""
    app = QApplication.instance() or QApplication(sys.argv)
    window = DashboardWindow(preview=True)
    if render:
        window.show()
        app.processEvents()
        window.grab().save(str(render))
        window.close()
        return 0
    window.show()
    return app.exec()
