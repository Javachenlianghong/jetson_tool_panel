from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_devices_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)
    window.device_profile_combo = QComboBox()
    window.device_name_edit = QLineEdit("Jetson")
    window.device_remote_edit = QLineEdit(window.remote_edit.text())
    window.device_remote_path_edit = QLineEdit(window.remote_path_edit.text())
    window.device_local_root_edit = QLineEdit(window.local_root_edit.text())

    grid.addWidget(QLabel("设备档案"), 0, 0)
    grid.addWidget(window.device_profile_combo, 0, 1)
    grid.addWidget(QLabel("名称"), 1, 0)
    grid.addWidget(window.device_name_edit, 1, 1)
    grid.addWidget(QLabel("SSH 地址"), 2, 0)
    grid.addWidget(window.device_remote_edit, 2, 1)
    grid.addWidget(QLabel("远端项目路径"), 3, 0)
    grid.addWidget(window.device_remote_path_edit, 3, 1)
    grid.addWidget(QLabel("本地项目路径"), 4, 0)
    grid.addWidget(window.device_local_root_edit, 4, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    for text, handler, primary in [
        ("保存档案", window.save_device_profile, True),
        ("加载档案", window.load_device_profile, True),
        ("删除档案", window.delete_device_profile, False),
        ("从当前配置填充", window.fill_device_profile_from_current, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 5, 0, 1, 2)

    layout.addWidget(build_panel("多设备配置", grid))
    layout.addWidget(build_note("设备档案用于保存多个设备配置。加载档案会同步更新窗口顶部的远端 SSH 地址、本地路径和远端项目路径。日常操作只需要在顶部确认远端 SSH。"))
    layout.addStretch(1)
    return page
