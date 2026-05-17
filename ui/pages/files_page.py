from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_files_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.remote_file_path_edit = QLineEdit("/home/jetson")
    window.local_file_path_edit = QLineEdit(str(window.paths.app_dir))

    grid.addWidget(QLabel("远端路径"), 0, 0)
    grid.addWidget(window.remote_file_path_edit, 0, 1)
    grid.addWidget(QLabel("本地路径"), 1, 0)
    grid.addWidget(window.local_file_path_edit, 1, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    specs = [
        ("列出", window.list_remote_files, True),
        ("新建目录", window.mkdir_remote_path, False),
        ("删除远端路径", window.remove_remote_path, False),
        ("上传文件", window.upload_single_file, True),
        ("下载文件", window.download_single_file, True),
    ]
    for text, handler, primary in specs:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 2, 0, 1, 2)

    layout.addWidget(build_panel("远程文件管理", grid))
    layout.addWidget(build_note("列出/新建/删除通过 SSH 执行；上传/下载使用 SCP。删除会弹出确认，避免误删。"))
    layout.addStretch(1)
    return page
