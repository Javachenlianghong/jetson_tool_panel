from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QKeySequence
from PyQt5.QtWidgets import (
    QAbstractItemView,
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
    QTreeWidget,
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


def _build_dir_tree():
    tree = QTreeWidget()
    tree.setHeaderLabel("目录树")
    tree.setAlternatingRowColors(True)
    tree.setUniformRowHeights(True)
    tree.setMinimumHeight(110)
    return tree


def _build_session_bar(window):
    layout = QHBoxLayout()
    layout.setSpacing(8)

    layout.addWidget(_tool_button("连接", window.terminal_connect, primary=True))
    layout.addWidget(_tool_button("断开", window.terminal_disconnect))
    layout.addWidget(_tool_button("Ctrl+C", window.terminal_interrupt))
    layout.addWidget(_tool_button("清屏", window.terminal_clear))
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

    window.terminal_output_edit = QPlainTextEdit()
    window.terminal_output_edit.setObjectName("TerminalOutput")
    window.terminal_output_edit.setReadOnly(True)
    window.terminal_output_edit.setLineWrapMode(QPlainTextEdit.NoWrap)
    terminal_font = QFont("Consolas")
    terminal_font.setStyleHint(QFont.Monospace)
    terminal_font.setPointSize(10)
    window.terminal_output_edit.setFont(terminal_font)

    command_row = QHBoxLayout()
    command_row.setSpacing(8)
    window.terminal_input_edit = QLineEdit()
    window.terminal_input_edit.setObjectName("TerminalInput")
    window.terminal_input_edit.setPlaceholderText("输入命令后按 Enter")
    window.terminal_input_edit.returnPressed.connect(window.terminal_send_command)
    QShortcut(QKeySequence("Ctrl+C"), window.terminal_input_edit, activated=window.terminal_interrupt)
    command_row.addWidget(window.terminal_input_edit, 1)
    command_row.addWidget(_tool_button("发送", window.terminal_send_command, primary=True))

    layout.addWidget(window.terminal_output_edit, 1)
    layout.addLayout(command_row)
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
    action_row.addWidget(_tool_button("终端进入", window.terminal_cd_remote_path))
    action_row.addWidget(_tool_button("新建目录", window.sftp_mkdir_remote))
    action_row.addWidget(_tool_button("删除远端", window.sftp_delete_remote))
    action_row.addWidget(_tool_button("复制路径", window.copy_remote_selected_paths))
    action_row.addStretch(1)
    window.remote_file_count_label = QLabel("共 0 项 | 目录 0 | 文件 0")
    window.remote_file_count_label.setObjectName("FileCountBadge")
    action_row.addWidget(window.remote_file_count_label)
    layout.addLayout(action_row)

    browser_splitter = QSplitter(Qt.Vertical)
    browser_splitter.setChildrenCollapsible(False)
    browser_splitter.setHandleWidth(6)

    window.remote_dir_tree = _build_dir_tree()
    window.remote_dir_tree.itemExpanded.connect(window.remote_dir_tree_expanded)
    window.remote_dir_tree.itemDoubleClicked.connect(window.remote_dir_tree_activated)
    browser_splitter.addWidget(window.remote_dir_tree)

    window.remote_files_table = _build_file_table()
    window.remote_files_table.itemDoubleClicked.connect(window.remote_file_item_activated)
    window.remote_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
    window.remote_files_table.customContextMenuRequested.connect(window.remote_files_context_menu)
    window.remote_files_table.itemSelectionChanged.connect(window.remote_file_selection_changed)
    browser_splitter.addWidget(window.remote_files_table)
    browser_splitter.setSizes([140, 320])
    layout.addWidget(browser_splitter, 1)

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
    window.local_file_count_label = QLabel("共 0 项 | 目录 0 | 文件 0")
    window.local_file_count_label.setObjectName("FileCountBadge")
    action_row.addWidget(window.local_file_count_label)
    layout.addLayout(action_row)

    browser_splitter = QSplitter(Qt.Vertical)
    browser_splitter.setChildrenCollapsible(False)
    browser_splitter.setHandleWidth(6)

    window.local_dir_tree = _build_dir_tree()
    window.local_dir_tree.itemExpanded.connect(window.local_dir_tree_expanded)
    window.local_dir_tree.itemDoubleClicked.connect(window.local_dir_tree_activated)
    browser_splitter.addWidget(window.local_dir_tree)

    window.local_files_table = _build_file_table()
    window.local_files_table.itemDoubleClicked.connect(window.local_file_item_activated)
    window.local_files_table.setContextMenuPolicy(Qt.CustomContextMenu)
    window.local_files_table.customContextMenuRequested.connect(window.local_files_context_menu)
    window.local_files_table.itemSelectionChanged.connect(window.local_file_selection_changed)
    browser_splitter.addWidget(window.local_files_table)
    browser_splitter.setSizes([130, 300])
    layout.addWidget(browser_splitter, 1)
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
    window.local_dir_tree = None
    window.remote_dir_tree = None
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
