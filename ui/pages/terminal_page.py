from PyQt5.QtCore import QEvent, QTimer, Qt
from PyQt5.QtGui import QColor, QFont, QKeySequence, QPainter
from PyQt5.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QPlainTextEdit,
    QShortcut,
    QSplitter,
    QSpinBox,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from core.vnc_client import VncDisplayWidget


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
    CURSOR_WIDTH = 2

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
        cursor_rect.setWidth(self.CURSOR_WIDTH)
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
            Qt.Key_Left: self._cursor_key_sequence("D"),
            Qt.Key_Right: self._cursor_key_sequence("C"),
            Qt.Key_Up: self._cursor_key_sequence("A"),
            Qt.Key_Down: self._cursor_key_sequence("B"),
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

    def _cursor_key_sequence(self, final):
        terminal_buffer = getattr(self.window, "terminal_buffer", None)
        if getattr(terminal_buffer, "application_cursor_keys", False):
            return "\x1bO" + final
        return "\x1b[" + final


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
    window.terminal_quick_command_combo = QComboBox()
    window.terminal_quick_command_combo.addItems([
        "pwd",
        "ls -lah",
        "cd 项目目录",
        "tegrastats",
        "检测 DISPLAY",
        "查看 run-control.log",
        "停止 tegrastats",
    ])
    layout.addWidget(window.terminal_quick_command_combo)
    layout.addWidget(_tool_button("发送", window.terminal_send_quick_command))
    layout.addWidget(_tool_button("cd 项目", window.terminal_cd_project))
    layout.addWidget(_tool_button("检测 DISPLAY", window.terminal_check_display))

    window.terminal_status_label = QLabel("未连接")
    window.terminal_status_label.setObjectName("MutedText")
    layout.addWidget(QLabel("会话"))
    layout.addWidget(window.terminal_status_label, 1)
    return _panel("会话", layout)


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


def _command_button(window, text, handler, primary=False):
    button = _tool_button(text, handler, primary=primary)
    window.command_buttons.append(button)
    return button


def _build_file_management_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    file_splitter = QSplitter(Qt.Vertical)
    file_splitter.setChildrenCollapsible(False)
    file_splitter.setHandleWidth(8)
    file_splitter.addWidget(_build_remote_files_panel(window))
    file_splitter.addWidget(_build_local_files_panel(window))
    file_splitter.setSizes([320, 300])

    layout.addWidget(file_splitter, 1)
    layout.addWidget(_build_transfer_bar(window), 0)
    return _panel("文件管理", layout)


def _build_ssh_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    layout.addWidget(_build_session_bar(window), 0)
    layout.addWidget(_build_terminal_panel(window), 1)
    return _panel("SSH", layout)


def _build_vnc_panel(window):
    layout = QVBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    grid = QGridLayout()
    grid.setHorizontalSpacing(8)
    grid.setVerticalSpacing(8)
    window.remote_desktop_display_edit = QLineEdit(":0")
    window.remote_desktop_display_edit.setMaximumWidth(76)
    window.remote_desktop_xauthority_edit = QLineEdit("/home/jetson/.Xauthority")
    window.remote_desktop_port_spin = QSpinBox()
    window.remote_desktop_port_spin.setRange(5900, 5999)
    window.remote_desktop_port_spin.setValue(5900)
    window.remote_desktop_port_spin.setMaximumWidth(82)
    window.remote_desktop_performance_combo = QComboBox()
    window.remote_desktop_performance_combo.addItems(["平衡 (75%)", "高清 (85%)", "流畅 (50%)", "清晰 (100%)"])
    window.remote_desktop_performance_combo.setMaximumWidth(120)
    window.remote_desktop_status_label = QLabel("未连接")
    window.remote_desktop_status_label.setObjectName("MutedText")

    grid.addWidget(QLabel("DISPLAY"), 0, 0)
    grid.addWidget(window.remote_desktop_display_edit, 0, 1)
    grid.addWidget(QLabel("端口"), 0, 2)
    grid.addWidget(window.remote_desktop_port_spin, 0, 3)
    grid.addWidget(QLabel("模式"), 0, 4)
    grid.addWidget(window.remote_desktop_performance_combo, 0, 5)
    grid.addWidget(QLabel("XAUTH"), 1, 0)
    grid.addWidget(window.remote_desktop_xauthority_edit, 1, 1, 1, 3)
    grid.addWidget(QLabel("状态"), 1, 4)
    grid.addWidget(window.remote_desktop_status_label, 1, 5)
    grid.setColumnStretch(3, 1)
    layout.addLayout(grid)

    install_row = QHBoxLayout()
    install_row.setSpacing(6)
    for text, handler, primary in [
        ("安装 x11vnc", window.install_remote_desktop_service, False),
        ("终端安装 x11vnc", window.install_remote_desktop_service_in_terminal, False),
        ("查询服务", window.query_remote_desktop_service, False),
    ]:
        install_row.addWidget(_command_button(window, text, handler, primary=primary))
    install_row.addStretch(1)
    layout.addLayout(install_row)

    connect_row = QHBoxLayout()
    connect_row.setSpacing(6)
    for text, handler, primary in [
        ("启动并连接", window.start_and_connect_remote_desktop, True),
        ("仅连接", window.connect_remote_desktop, True),
        ("断开", window.disconnect_remote_desktop, False),
        ("停止服务", window.stop_remote_desktop_service, False),
    ]:
        connect_row.addWidget(_command_button(window, text, handler, primary=primary))
    connect_row.addStretch(1)
    layout.addLayout(connect_row)

    window.remote_desktop_view = VncDisplayWidget()
    window.remote_desktop_view.setMinimumHeight(260)
    layout.addWidget(window.remote_desktop_view, 1)
    return _panel("VNC", layout)


def _toggle_splitter_side(splitter, index, button, collapse_text, expand_text, fallback_width):
    sizes = splitter.sizes()
    if len(sizes) < 3:
        return
    center_index = 1
    if sizes[index] <= 0:
        restore_width = int(button.property("restoreWidth") or fallback_width)
        sizes[index] = max(restore_width, 180)
        sizes[center_index] = max(260, sizes[center_index] - sizes[index])
        button.setText(collapse_text)
    else:
        button.setProperty("restoreWidth", max(sizes[index], fallback_width))
        sizes[center_index] += sizes[index]
        sizes[index] = 0
        button.setText(expand_text)
    splitter.setSizes(sizes)


def _build_three_pane_toolbar(main_splitter):
    layout = QHBoxLayout()
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    file_button = QPushButton("收起文件管理")
    file_button.setObjectName("ToggleFilePaneButton")
    file_button.clicked.connect(
        lambda _checked=False: _toggle_splitter_side(
            main_splitter, 0, file_button, "收起文件管理", "展开文件管理", 420
        )
    )

    vnc_button = QPushButton("收起 VNC")
    vnc_button.setObjectName("ToggleVncPaneButton")
    vnc_button.clicked.connect(
        lambda _checked=False: _toggle_splitter_side(main_splitter, 2, vnc_button, "收起 VNC", "展开 VNC", 520)
    )

    hint = QLabel("三块工作区：文件管理 / SSH / VNC")
    hint.setObjectName("MutedText")
    layout.addWidget(file_button)
    layout.addWidget(vnc_button)
    layout.addWidget(hint)
    layout.addStretch(1)
    return layout


def build_terminal_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)

    window.local_files_table = None
    window.remote_files_table = None
    window.files_summary_label = None
    window.files_table = None

    main_splitter = QSplitter(Qt.Horizontal)
    main_splitter.setObjectName("WorkbenchThreePaneSplitter")
    main_splitter.setChildrenCollapsible(True)
    main_splitter.setHandleWidth(8)

    main_splitter.addWidget(_build_file_management_panel(window))
    main_splitter.addWidget(_build_ssh_panel(window))
    main_splitter.addWidget(_build_vnc_panel(window))
    main_splitter.setCollapsible(0, True)
    main_splitter.setCollapsible(1, False)
    main_splitter.setCollapsible(2, True)
    main_splitter.setSizes([420, 560, 520])
    window.workbench_three_pane_splitter = main_splitter
    layout.addLayout(_build_three_pane_toolbar(main_splitter), 0)
    layout.addWidget(main_splitter, 1)

    return page
