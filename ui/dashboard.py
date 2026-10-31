"""Clicky's additive native control dashboard, using existing app callbacks."""
from datetime import datetime
import json
from pathlib import Path
import sys
from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QFont, QKeySequence, QShortcut
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout,
    QGridLayout, QLabel, QPushButton, QFrame, QListWidget, QStackedWidget,
    QPlainTextEdit, QLineEdit, QTableWidget, QTableWidgetItem, QHeaderView,
    QAbstractItemView, QScrollArea, QListWidgetItem, QComboBox)

from classroom.settings import data_root
from classroom.session import Session
from ui.dashboard_icons import icon

STYLE = '''
QWidget#dashboard { background:#191b1c; color:#eeeeef; }
QWidget { font-family:"Segoe UI"; font-size:13px; color:#eeeeef; }
QFrame#sidebar { background:#111314; border-right:1px solid #2d3032; }
QFrame#noteRail { background:#191b1c; border-right:1px solid #2d3032; }
QFrame#topbar { background:#191b1c; border-bottom:1px solid #2d3032; }
QLabel#brand { font-size:20px; font-weight:600; }
QLabel#pageTitle { font-size:26px; font-weight:600; }
QLabel#sectionTitle { font-size:15px; font-weight:600; }
QLabel#secondary { color:#93969b; }
QLabel#value { font-size:20px; font-weight:600; }
QLabel#notice { background:#30271b; color:#f1ce95; padding:12px; border-radius:4px; }
QFrame#surface { background:#202224; border:1px solid #303336; border-radius:8px; }
QPushButton { background:#252729; border:1px solid #383b3f; border-radius:8px; padding:7px 12px; min-height:20px; }
QPushButton:hover { background:#303336; border-color:#575d64; }
QPushButton:focus { border:1px solid #65a5ff; }
QPushButton:disabled { color:#64696f; border-color:#303336; background:#202224; }
QPushButton#primary { background:#0078ff; color:white; border-color:#0078ff; }
QPushButton#primary:hover { background:#218aff; }
QListWidget { background:transparent; border:0; outline:0; }
QListWidget::item { height:40px; padding-left:12px; color:#c8c9ce; border-radius:6px; }
QListWidget::item:selected { background:#1c2a3b; color:#f0f0f5; }
QListWidget::item:hover:!selected { background:#232629; }
QListWidget#noteList::item { height:40px; padding-left:8px; }
QPlainTextEdit, QTextBrowser, QLineEdit, QTableWidget, QComboBox, QSpinBox { background:#202224; color:#eeeeef; border:1px solid #383b3f; border-radius:6px; padding:8px; }
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
QLineEdit#search { background:#252729; border:1px solid #3a3c3f; border-radius:18px; padding:8px 14px; }
QLineEdit#noteTitle { background:transparent; border:0; border-radius:0; font-size:32px; font-weight:600; padding:0; }
QLabel#pill { background:#252729; border-radius:14px; color:#aeb1b5; padding:6px 12px; }
QLabel#eyebrow { color:#8c9198; font-size:11px; font-weight:600; }
QPushButton#quiet { background:transparent; border:0; text-align:left; color:#bfc2c7; }
QPushButton#quiet:hover { background:#252729; }
QPushButton#record { background:#1e3049; border:1px solid #38577a; border-radius:18px; color:#d8e7ff; }
QTabWidget#noteTabs::pane { border:0; background:#191b1c; }
QTabWidget#noteTabs QTabBar::tab { background:#252729; color:#969ba1; padding:8px 14px; border-radius:14px; margin-right:4px; }
QTabWidget#noteTabs QTabBar::tab:selected { background:#30353b; color:#f3f4f5; }
QTextBrowser#transcriptReader, QPlainTextEdit#noteEditor { background:#191b1c; border:0; padding:16px 0; font-size:15px; selection-background-color:#24548a; }
QMenu { background:#222527; border:1px solid #3a3e42; padding:6px; }
QMenu::item { padding:8px 20px; }
QMenu::item:selected { background:#1c2a3b; }
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
    NAV_LABELS = ['Home','Chat','Notes','Library','Tools','Settings']

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
        self.resize(1440,900)
        self.setMinimumSize(1000,700)
        self.setStyleSheet(STYLE)
        root = QHBoxLayout(self)
        root.setContentsMargins(0,0,0,0)
        root.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName('sidebar')
        sidebar.setFixedWidth(184)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(12,24,12,16)
        side.setSpacing(24)
        brand = label('Clicky','brand')
        brand.setContentsMargins(12,0,0,8)
        side.addWidget(brand)
        self.navigation = QListWidget()
        self.navigation.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        for title, symbol in zip(self.NAV_LABELS, ['house','message-square','notebook-pen','library','blocks','settings-2']):
            self.navigation.addItem(QListWidgetItem(icon(symbol), title))
        self.navigation.setIconSize(QSize(19,19))
        self.navigation.setSpacing(4)
        self.navigation.setAccessibleName('Dashboard navigation')
        side.addWidget(self.navigation,1)
        self.mode = label('Preview — controls are not connected' if preview else 'Your desktop companion')
        side.addWidget(self.mode)
        self.menu_button = self.action_button('All Clicky controls','all_controls')
        side.addWidget(self.menu_button)
        root.addWidget(sidebar)
        content = QVBoxLayout()
        content.setContentsMargins(0,0,0,0)
        content.setSpacing(0)
        topbar = QFrame()
        topbar.setObjectName('topbar')
        topbar.setFixedHeight(64)
        top = QHBoxLayout(topbar)
        top.setContentsMargins(24,12,24,12)
        self.section_name = label('Home','sectionTitle')
        top.addWidget(self.section_name)
        top.addStretch()
        self.note_search = QLineEdit()
        self.note_search.setObjectName('search')
        self.note_search.setPlaceholderText('Search notes and transcripts…')
        self.note_search.setAccessibleName('Search saved notes and transcripts')
        self.note_search.addAction(icon('search'),QLineEdit.ActionPosition.LeadingPosition)
        self.note_search.setMinimumWidth(220)
        self.note_search.setMaximumWidth(420)
        self.note_search.textChanged.connect(self.filter_notes)
        top.addWidget(self.note_search,1)
        self.new_note_button = QPushButton('New note')
        self.new_note_button.setIcon(icon('plus','#d5d8dc'))
        self.new_note_button.clicked.connect(self.new_note)
        top.addWidget(self.new_note_button)
        content.addWidget(topbar)
        workspace = QHBoxLayout()
        workspace.setSpacing(0)
        self.note_rail = QFrame()
        self.note_rail.setObjectName('noteRail')
        self.note_rail.setFixedWidth(224)
        rail = QVBoxLayout(self.note_rail)
        rail.setContentsMargins(12,24,12,16)
        rail.setSpacing(16)
        rail.addWidget(label('PRIVATE NOTES','eyebrow'))
        self.all_notes_button = QPushButton('All class notes')
        self.all_notes_button.setObjectName('quiet')
        self.all_notes_button.setIcon(icon('folder'))
        self.all_notes_button.clicked.connect(self.clear_note_filters)
        rail.addWidget(self.all_notes_button)
        self.folder_filter=QComboBox()
        self.folder_filter.setAccessibleName('Filter notes by folder')
        self.folder_filter.addItem('All folders','')
        self.folder_filter.currentIndexChanged.connect(lambda:self.filter_notes(self.note_search.text()))
        rail.addWidget(self.folder_filter)
        self.note_list = QListWidget()
        self.note_list.setObjectName('noteList')
        self.note_list.setIconSize(QSize(17,17))
        self.note_list.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.note_list.itemClicked.connect(self.open_note_item)
        rail.addWidget(self.note_list,1)
        self.note_list_empty = label('Your saved classes will appear here.')
        rail.addWidget(self.note_list_empty)
        self.import_note_button = QPushButton('Import audio')
        self.import_note_button.setIcon(icon('upload'))
        self.import_note_button.clicked.connect(self.import_note)
        rail.addWidget(self.import_note_button)
        self.openwhispr_import_button=QPushButton('Import OpenWhispr notes')
        self.openwhispr_import_button.setObjectName('quiet')
        self.openwhispr_import_button.clicked.connect(self.import_openwhispr)
        rail.addWidget(self.openwhispr_import_button)
        rail.addWidget(label('Saved on this laptop','secondary'))
        workspace.addWidget(self.note_rail)
        self.stack = QStackedWidget()
        workspace.addWidget(self.stack,1)
        content.addLayout(workspace,1)
        root.addLayout(content,1)
        self._build_overview()
        self._build_assistant()
        self.classroom_slot = QWidget()
        slot_layout = QVBoxLayout(self.classroom_slot)
        slot_layout.setContentsMargins(0,0,0,0)
        self.classroom_slot_layout = slot_layout
        self.stack.addWidget(self.classroom_slot)
        self._build_library()
        self._build_tools()
        self._build_settings()
        self.navigation.currentRowChanged.connect(self._navigate)
        self.navigation.setCurrentRow(self.PAGES.index('Classroom'))
        self.search_shortcut = QShortcut(QKeySequence('Ctrl+K'),self)
        self.search_shortcut.activated.connect(self.focus_note_search)
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
        notes_page = self.PAGES[row] in {'Classroom','Class library'}
        self.note_rail.setVisible(notes_page)
        self.note_search.setVisible(notes_page)
        self.section_name.setText(self.NAV_LABELS[row])
        if self.PAGES[row] == 'Classroom' and self.classroom is None:
            from classroom.ui import ClassroomWindow
            self.classroom = self.classroom_factory() if self.classroom_factory else ClassroomWindow()
            self.classroom.intro.hide()
            self.classroom.setWindowFlags(Qt.WindowType.Widget)
            self.classroom_slot_layout.addWidget(self.classroom,1)
            self.classroom.messages.status.connect(self.record_activity)
            self.classroom.session_changed.connect(self.refresh_library)
        if self.PAGES[row] == 'Class library':
            self.refresh_library()
        self.stack.setCurrentIndex(row)

    def focus_note_search(self):
        self.select_page('Classroom')
        self.note_search.setFocus()

    def new_note(self):
        self.select_page('Classroom')
        if self.classroom.new_draft():
            self.clear_note_filters()
            self.note_list.clearSelection()
            self.classroom.title.setFocus()
            self.classroom.title.selectAll()

    def import_note(self):
        self.select_page('Classroom')
        if self.classroom.busy:
            self.classroom._message('Finish the active class before importing another.')
            return
        self.classroom._import()

    def import_openwhispr(self):
        self.select_page('Classroom')
        self.classroom._import_openwhispr()

    def clear_note_filters(self):
        self.note_search.clear()
        self.folder_filter.setCurrentIndex(0)

    def filter_notes(self, query=''):
        query = query.casefold().strip()
        self.note_list.clear()
        for index, (session, values) in enumerate(self.library_rows):
            folder=session.metadata.get('folder') or 'Clicky notes'
            if self.folder_filter.currentData() and self.folder_filter.currentData()!=folder:
                continue
            if query and query not in self.note_index.get(str(session.path),''):
                continue
            item = QListWidgetItem(icon('file-text'),values[0])
            item.setToolTip(values[0]+'\n'+values[1]+' · '+values[2])
            item.setData(Qt.ItemDataRole.UserRole,index)
            self.note_list.addItem(item)
            if self.classroom and self.classroom.session and self.classroom.session.path == session.path:
                item.setSelected(True)
        self.note_list_empty.setVisible(not self.note_list.count())
        self.note_list_empty.setText('No matching notes.' if query else 'Your saved classes will appear here.')

    def open_note_item(self, item):
        index = item.data(Qt.ItemDataRole.UserRole)
        if not isinstance(index,int) or not 0 <= index < len(self.library_rows):
            return
        self.select_page('Classroom')
        self.classroom._set_session(self.library_rows[index][0])
        self.filter_notes(self.note_search.text())

    def refresh_library(self):
        rows = []
        self.note_index = {}
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
                    searchable = [session.metadata.get('title','')]
                    for filename in ['transcript.md','notes.md']:
                        document = path/filename
                        if document.exists():
                            with document.open('r',encoding='utf-8') as stream:
                                searchable.append(stream.read(2_000_000))
                    self.note_index[str(path)] = '\n'.join(searchable).casefold()
                except (OSError, ValueError, KeyError):
                    errors += 1
        self.library_rows = rows
        def created_key(row):
            try:
                return datetime.fromisoformat(row[0].metadata.get('created','').replace('Z','+00:00')).timestamp()
            except (ValueError,OverflowError,OSError):
                return 0
        rows.sort(key=created_key,reverse=True)
        selected=self.folder_filter.currentData()
        self.folder_filter.blockSignals(True)
        self.folder_filter.clear()
        self.folder_filter.addItem('All folders','')
        for folder in sorted({session.metadata.get('folder') or 'Clicky notes' for session,_ in rows}):
            self.folder_filter.addItem(folder,folder)
        self.folder_filter.setCurrentIndex(max(0,self.folder_filter.findData(selected)))
        self.folder_filter.blockSignals(False)
        self.library.setRowCount(len(rows))
        for index, (_, values) in enumerate(rows):
            for column, value in enumerate(values):
                self.library.setItem(index,column,QTableWidgetItem(str(value)))
        self.library_empty.setVisible(not rows)
        self.open_class_button.setEnabled(bool(rows))
        self.values['saved'].setText(str(len(rows)))
        self.filter_notes(self.note_search.text())
        if errors:
            self.record_activity(f'{errors} saved class folder(s) could not be read. Check the folder before retrying.',error=True)

    def open_selected_class(self, *args):
        row = self.library.currentRow()
        if not 0 <= row < len(self.library_rows):
            return
        self.select_page('Classroom')
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
            if self.classroom and self.classroom.session:
                paths = {session.path for session,_ in self.library_rows}
                if self.classroom.session.path not in paths:
                    self.refresh_library()
        except Exception as exc:
            self.freshness.setText('State unavailable · '+datetime.now().strftime('%H:%M:%S'))
            self.record_activity('Could not refresh app state: '+str(exc),error=True)

    def closeEvent(self, event):
        if self.classroom and self.classroom.notes.document().isModified():
            self.classroom._save_notes()
            if self.classroom.notes.document().isModified():
                event.ignore()
                return
        if self.classroom:
            self.classroom.options_dialog.hide()
        event.accept()


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
