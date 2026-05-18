from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QShortcut,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)


def _tool_button(text, handler, primary=False):
    button = QPushButton(text)
    if primary:
        button.setObjectName("PrimaryButton")
    button.clicked.connect(lambda _checked=False: handler())
    return button


def _panel(title, content_layout):
    panel = QFrame()
    panel.setObjectName("Panel")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 8, 10, 10)
    layout.setSpacing(8)
    title_label = QLabel(title)
    title_label.setObjectName("PanelTitle")
    layout.addWidget(title_label)
    layout.addLayout(content_layout, 1)
    return panel


def _build_file_table(minimum_height=120):
    table = QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "权限"])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
    table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
    table.setMinimumHeight(minimum_height)
    return table


class TerminalOutput(QPlainTextEdit):
    def __init__(self, window):
        super().__init__()
        self.window = window
        self._cursor_visible = True
        self._cursor_timer = QTimer(self)
        self._cursor_timer.timeout.connect(self._blink_cursor)
        self._cursor_timer.start(500)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setTabChangesFocus(False)

    def _blink_cursor(self):
        self._cursor_visible = not self._cursor_visible
        self.viewport().update()

    def focusInEvent(self, event):
        self._cursor_visible = True
        self.viewport().update()
        super().focusInEvent(event)

    def focusOutEvent(self, event):
        self._cursor_visible = False
        self.viewport().update()
        super().focusOutEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        if not self._cursor_visible or not self.hasFocus():
            return
        cursor_rect = self.cursorRect(self.textCursor())
        cursor_rect.setWidth(8)
        painter = QPainter(self.viewport())
        painter.fillRect(cursor_rect, QColor("#e5e7eb"))

    def event(self, event):
        if event.type() == QEvent.KeyPress and event.key() in (Qt.Key_Tab, Qt.Key_Backtab):
            self.window.terminal_send_text("\t" if event.key() == Qt.Key_Tab else "\x1b[Z")
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        modifiers = event.modifiers()
        ctrl = bool(modifiers & Qt.ControlModifier)
        shift = bool(modifiers & Qt.ShiftModifier)

        if ctrl and shift and key == Qt.Key_C:
            self.copy()
            event.accept()
            return
        if (ctrl and key == Qt.Key_V) or (ctrl and shift and key == Qt.Key_V):
            text = QApplication.clipboard().text()
            if text:
                self.window.terminal_send_text(text.replace("\r\n", "\n").replace("\r", "\n"))
            event.accept()
            return
        if ctrl and key == Qt.Key_C:
            self.window.terminal_interrupt()
            event.accept()
            return

        special_keys = {
            Qt.Key_Return: "\r",
            Qt.Key_Enter: "\r",
            Qt.Key_Backspace: "\x7f",
            Qt.Key_Tab: "\t",
            Qt.Key_Left: "\x1b[D",
            Qt.Key_Right: "\x1b[C",
            Qt.Key_Up: "\x1b[A",
            Qt.Key_Down: "\x1b[B",
            Qt.Key_Home: "\x1b[H",
            Qt.Key_End: "\x1b[F",
            Qt.Key_Delete: "\x1b[3~",
            Qt.Key_PageUp: "\x1b[5~",
            Qt.Key_PageDown: "\x1b[6~",
            Qt.Key_Escape: "\x1b",
        }
        if key in special_keys:
            self.window.terminal_send_text(special_keys[key])
            event.accept()
            return

        if ctrl and Qt.Key_A <= key <= Qt.Key_Z:
            self.window.terminal_send_text(chr(key - Qt.Key_A + 1))
            event.accept()
            return

        text = event.text()
        if text and not (modifiers & Qt.AltModifier):
            self.window.terminal_send_text(text)
            event.accept()
            return

        super().keyPressEvent(event)


def _build_session_bar(window):
    layout = QHBoxLayout()
    layout.setSpacing(8)

    layout.addWidget(_tool_button("连接", window.terminal_connect, primary=True))
    layout.addWidget(_tool_button("断开", window.terminal_disconnect))
    layout.addWidget(_tool_button("Ctrl+C", window.terminal_interrupt))
    layout.addWidget(_tool_button("清屏", window.terminal_clear))
    layout.addSpacing(10)
    sync_button = _tool_button("同步到 Jetson", window.sync_to_jetson, primary=True)
    window.command_buttons.append(sync_button)
    layout.addWidget(sync_button)
    layout.addSpacing(10)

    window.terminal_export_display_check = QCheckBox("连接后导出 DISPLAY")
    window.terminal_export_display_check.setToolTip(
        "SSH 终端连接成功后发送 export DISPLAY=:0 和 export XAUTHORITY=/home/jetson/.Xauthority"
    )
    window.terminal_export_display_check.clicked.connect(lambda _checked: window._save_settings())
    layout.addWidget(window.terminal_export_display_check)
    layout.addSpacing(10)

    window.terminal_status_label = QLabel("未连接")
    window.terminal_status_label.setObjectName("MutedText")
    layout.addWidget(QLabel("会话"))
    layout.addWidget(window.terminal_status_label, 1)
    return _panel("SSH 会话", layout)


def _build_terminal_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    window.terminal_output_edit = TerminalOutput(window)
    window.terminal_output_edit.setObjectName("TerminalOutput")
    window.terminal_output_edit.setReadOnly(True)
    window.terminal_output_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
    terminal_font = QFont("Consolas")
    terminal_font.setStyleHint(QFont.Monospace)
    terminal_font.setPointSize(10)
    window.terminal_output_edit.setFont(terminal_font)

    QShortcut(QKeySequence("Ctrl+C"), window.terminal_output_edit, activated=window.terminal_interrupt)

    layout.addWidget(window.terminal_output_edit, 1)
    return _panel("终端", layout)


def _build_remote_files_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    path_row = QHBoxLayout()
    path_row.setSpacing(6)
    window.remote_file_path_edit = QLineEdit("/home/jetson")
    window.remote_file_path_edit.returnPressed.connect(window.refresh_remote_files)
    path_row.addWidget(window.remote_file_path_edit, 1)
    path_row.addWidget(_tool_button("上级", window.remote_files_up))
    path_row.addWidget(_tool_button("刷新", window.refresh_remote_files, primary=True))
    layout.addLayout(path_row)

    action_row = QHBoxLayout()
    action_row.setSpacing(6)
    action_row.addWidget(_tool_button("本地预览", window.preview_remote_selected_file, primary=True))
    action_row.addWidget(_tool_button("进入目录", window.remote_open_selected_path))
    action_row.addWidget(_tool_button("新建目录", window.sftp_mkdir_remote))
    action_row.addWidget(_tool_button("删除远端", window.sftp_delete_remote))
    action_row.addWidget(_tool_button("复制路径", window.copy_remote_selected_paths))
    action_row.addStretch(1)
    layout.addLayout(action_row)

    window.remote_files_table = _build_file_table()
    window.remote_files_table.itemDoubleClicked.connect(window.remote_file_item_activated)
    window.remote_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
    window.remote_files_table.customContextMenuRequested.connect(window.remote_files_context_menu)
    window.remote_files_table.itemSelectionChanged.connect(window.remote_file_selection_changed)
    layout.addWidget(window.remote_files_table, 1)

    bookmark_row = QHBoxLayout()
    bookmark_row.setSpacing(6)
    window.remote_path_bookmark_combo = QComboBox()
    bookmark_row.addWidget(window.remote_path_bookmark_combo, 1)
    bookmark_row.addWidget(_tool_button("使用", window.apply_remote_path_bookmark))
    bookmark_row.addWidget(_tool_button("保存", window.save_remote_path_bookmark))
    bookmark_row.addWidget(_tool_button("删除", window.delete_remote_path_bookmark))
    layout.addLayout(bookmark_row)
    return _panel("远端文件", layout)


def _build_local_files_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    path_row = QHBoxLayout()
    path_row.setSpacing(6)
    window.local_file_path_edit = QLineEdit(str(window.paths.app_dir))
    window.local_file_path_edit.returnPressed.connect(window.refresh_local_files)
    path_row.addWidget(window.local_file_path_edit, 1)
    path_row.addWidget(_tool_button("上级", window.local_files_up))
    path_row.addWidget(_tool_button("浏览", window.browse_local_file_dir))
    path_row.addWidget(_tool_button("刷新", window.refresh_local_files))
    layout.addLayout(path_row)

    action_row = QHBoxLayout()
    action_row.setSpacing(6)
    action_row.addWidget(_tool_button("上传 ->", window.sftp_upload_selected, primary=True))
    action_row.addWidget(_tool_button("<- 下载", window.sftp_download_selected, primary=True))
    action_row.addWidget(_tool_button("删除本地", window.delete_local_selected))
    action_row.addWidget(_tool_button("打开位置", window.open_local_selected_path))
    action_row.addWidget(_tool_button("复制路径", window.copy_local_selected_paths))
    action_row.addStretch(1)
    layout.addLayout(action_row)

    window.local_files_table = _build_file_table()
    window.local_files_table.itemDoubleClicked.connect(window.local_file_item_activated)
    window.local_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
    window.local_files_table.customContextMenuRequested.connect(window.local_files_context_menu)
    window.local_files_table.itemSelectionChanged.connect(window.local_file_selection_changed)
    layout.addWidget(window.local_files_table, 1)
    return _panel("本地文件", layout)


def _build_transfer_bar(window):
    layout = QHBoxLayout()
    layout.setSpacing(8)
    window.files_summary_label = QLabel("就绪")
    window.files_summary_label.setObjectName("MutedText")
    window.transfer_progress_bar = QProgressBar()
    window.transfer_progress_bar.setRange(0, 100)
    window.transfer_progress_bar.setValue(0)
    layout.addWidget(window.files_summary_label, 1)
    layout.addWidget(window.transfer_progress_bar)
    layout.addWidget(_tool_button("取消传输", window.sftp_cancel_transfer))
    return _panel("传输", layout)


def build_terminal_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    window.local_files_table = None
    window.remote_files_table = None
    window.files_summary_label = None
    window.files_table = None

    layout.addWidget(_build_session_bar(window))

    main_splitter = QSplitter(Qt.Horizontal)
    main_splitter.setChildrenCollapsible(False)
    main_splitter.setHandleWidth(8)

    file_splitter = QSplitter(Qt.Vertical)
    file_splitter.setChildrenCollapsible(False)
    file_splitter.setHandleWidth(8)
    file_splitter.addWidget(_build_remote_files_panel(window))
    file_splitter.addWidget(_build_local_files_panel(window))
    file_splitter.setSizes([320, 300])

    terminal_column = QSplitter(Qt.Vertical)
    terminal_column.setChildrenCollapsible(False)
    terminal_column.setHandleWidth(8)
    terminal_column.addWidget(_build_terminal_panel(window))
    terminal_column.addWidget(_build_transfer_bar(window))
    terminal_column.setSizes([620, 90])

    main_splitter.addWidget(file_splitter)
    main_splitter.addWidget(terminal_column)
    main_splitter.setSizes([430, 820])
    layout.addWidget(main_splitter, 1)

    return page
