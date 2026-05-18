from PyQt5.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt

from ui.pages.common import build_note, build_panel


def _build_file_table():
    table = QTableWidget(0, 4)
    table.setHorizontalHeaderLabels(["名称", "大小", "修改时间", "权限"])
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectRows)
    table.setSelectionMode(QAbstractItemView.ExtendedSelection)
    table.setAlternatingRowColors(True)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
    table.setMinimumHeight(260)
    return table


def build_files_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    window.local_files_table = None
    window.remote_files_table = None
    window.files_summary_label = None
    window.files_table = None

    splitter = QSplitter(Qt.Horizontal)
    splitter.setChildrenCollapsible(False)

    local_panel = QWidget()
    local_layout = QVBoxLayout(local_panel)
    local_layout.setContentsMargins(0, 0, 0, 0)
    local_layout.setSpacing(8)
    local_path_row = QHBoxLayout()
    window.local_file_path_edit = QLineEdit(str(window.paths.app_dir))
    window.local_file_path_edit.returnPressed.connect(window.refresh_local_files)
    local_up_button = QPushButton("上级")
    local_up_button.clicked.connect(window.local_files_up)
    local_browse_button = QPushButton("浏览")
    local_browse_button.clicked.connect(window.browse_local_file_dir)
    local_refresh_button = QPushButton("刷新")
    local_refresh_button.clicked.connect(window.refresh_local_files)
    local_path_row.addWidget(QLabel("本地"))
    local_path_row.addWidget(window.local_file_path_edit, 1)
    local_path_row.addWidget(local_up_button)
    local_path_row.addWidget(local_browse_button)
    local_path_row.addWidget(local_refresh_button)
    window.local_files_table = _build_file_table()
    window.local_files_table.itemDoubleClicked.connect(window.local_file_item_activated)
    local_layout.addLayout(local_path_row)
    local_layout.addWidget(window.local_files_table, 1)

    remote_panel = QWidget()
    remote_layout = QVBoxLayout(remote_panel)
    remote_layout.setContentsMargins(0, 0, 0, 0)
    remote_layout.setSpacing(8)
    remote_path_row = QHBoxLayout()
    window.remote_file_path_edit = QLineEdit("/home/jetson")
    window.remote_file_path_edit.returnPressed.connect(window.refresh_remote_files)
    remote_up_button = QPushButton("上级")
    remote_up_button.clicked.connect(window.remote_files_up)
    remote_refresh_button = QPushButton("刷新")
    remote_refresh_button.setObjectName("PrimaryButton")
    remote_refresh_button.clicked.connect(window.refresh_remote_files)
    remote_path_row.addWidget(QLabel("远端"))
    remote_path_row.addWidget(window.remote_file_path_edit, 1)
    remote_path_row.addWidget(remote_up_button)
    remote_path_row.addWidget(remote_refresh_button)
    window.remote_files_table = _build_file_table()
    window.remote_files_table.itemDoubleClicked.connect(window.remote_file_item_activated)
    remote_layout.addLayout(remote_path_row)
    remote_layout.addWidget(window.remote_files_table, 1)

    splitter.addWidget(local_panel)
    splitter.addWidget(remote_panel)
    splitter.setSizes([520, 520])
    layout.addWidget(build_panel("双栏文件传输", _wrap_widget(splitter)), 1)

    ops = QGridLayout()
    ops.setHorizontalSpacing(10)
    ops.setVerticalSpacing(10)
    upload_button = QPushButton("上传 ->")
    upload_button.setObjectName("PrimaryButton")
    upload_button.clicked.connect(window.sftp_upload_selected)
    download_button = QPushButton("<- 下载")
    download_button.setObjectName("PrimaryButton")
    download_button.clicked.connect(window.sftp_download_selected)
    mkdir_button = QPushButton("新建远端目录")
    mkdir_button.clicked.connect(window.sftp_mkdir_remote)
    delete_remote_button = QPushButton("删除远端")
    delete_remote_button.clicked.connect(window.sftp_delete_remote)
    delete_local_button = QPushButton("删除本地")
    delete_local_button.clicked.connect(window.delete_local_selected)
    cancel_button = QPushButton("取消传输")
    cancel_button.clicked.connect(window.sftp_cancel_transfer)
    transfer_buttons = [
        upload_button,
        download_button,
        mkdir_button,
        delete_remote_button,
        delete_local_button,
        cancel_button,
    ]
    for index, button in enumerate(transfer_buttons):
        ops.addWidget(button, 0, index)
    window.files_summary_label = QLabel("左侧本地，右侧远端。双击目录进入，选择文件后上传或下载。")
    window.files_summary_label.setObjectName("MutedText")
    window.transfer_progress_bar = QProgressBar()
    window.transfer_progress_bar.setRange(0, 100)
    window.transfer_progress_bar.setValue(0)
    ops.addWidget(window.files_summary_label, 1, 0, 1, 3)
    ops.addWidget(window.transfer_progress_bar, 1, 3, 1, 3)
    layout.addWidget(build_panel("传输操作", ops))

    bookmark_row = QHBoxLayout()
    window.remote_path_bookmark_combo = QComboBox()
    bookmark_row.addWidget(QLabel("远端收藏"))
    bookmark_row.addWidget(window.remote_path_bookmark_combo, 1)
    for text, handler in [
        ("使用收藏", window.apply_remote_path_bookmark),
        ("保存当前路径", window.save_remote_path_bookmark),
        ("删除收藏", window.delete_remote_path_bookmark),
    ]:
        button = QPushButton(text)
        button.clicked.connect(handler)
        bookmark_row.addWidget(button)
    layout.addWidget(build_panel("路径收藏", bookmark_row))
    layout.addWidget(build_note("文件传输使用 SFTP。远端删除仍会拒绝系统根目录、相对路径和包含 '..' 的危险路径。密码只用于当前连接，不会保存。"))
    return page


def _wrap_widget(widget):
    layout = QVBoxLayout()
    layout.addWidget(widget)
    return layout
