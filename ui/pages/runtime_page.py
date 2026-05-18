from PyQt5.QtWidgets import QCheckBox, QGridLayout, QHBoxLayout, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_runtime_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)

    window.run_workdir_edit = QLineEdit(window.remote_path_edit.text())
    window._bind_line_edits(window.remote_path_edit, window.run_workdir_edit)
    window.run_command_edit = QLineEdit("python3 detect.py")
    window.run_background_check = QCheckBox("后台运行并写入 run-control.log")

    grid.addWidget(QLabel("远程目录"), 0, 0)
    grid.addWidget(window.run_workdir_edit, 0, 1)
    grid.addWidget(QLabel("启动命令"), 1, 0)
    grid.addWidget(window.run_command_edit, 1, 1)
    grid.addWidget(QLabel("运行方式"), 2, 0)
    grid.addWidget(window.run_background_check, 2, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    run_button = QPushButton("运行命令")
    run_button.setObjectName("PrimaryButton")
    run_button.clicked.connect(window.run_remote_program)
    stop_hint_button = QPushButton("停止当前命令")
    stop_hint_button.clicked.connect(window.stop_current_command)
    for button in (run_button, stop_hint_button):
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 3, 0, 1, 2)

    layout.addWidget(build_panel("远程运行控制", grid))
    result_layout = QVBoxLayout()
    window.runtime_result_text = QPlainTextEdit()
    window.runtime_result_text.setReadOnly(True)
    window.runtime_result_text.setMinimumHeight(140)
    window.runtime_result_text.setPlainText("运行命令后显示 FPS、PID、日志路径、DISPLAY/CUDA/文件路径等诊断结果。")
    result_layout.addWidget(window.runtime_result_text)
    layout.addWidget(build_panel("运行结果", result_layout))
    layout.addWidget(build_note("前台运行会持续占用底部日志区；后台运行会返回 PID，并把输出写到远端目录的 run-control.log。"))
    layout.addStretch(1)
    return page
