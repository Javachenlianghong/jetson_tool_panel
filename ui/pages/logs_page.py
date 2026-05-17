from PyQt5.QtWidgets import QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget

from ui.pages.common import build_note, build_panel


def build_logs_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)

    grid = QGridLayout()
    grid.setHorizontalSpacing(10)
    grid.setVerticalSpacing(10)

    window.log_tail_target_combo = QComboBox()
    window.log_tail_target_combo.setEditable(True)
    window.log_tail_target_combo.addItems([
        "/var/log/syslog",
        "/tmp/run-control.log",
        "run-control.log",
        "journal:",
        "journal:your-service.service",
        "dmesg",
    ])
    window.log_tail_lines_spin = QSpinBox()
    window.log_tail_lines_spin.setRange(1, 2000)
    window.log_tail_lines_spin.setValue(120)

    grid.addWidget(QLabel("日志目标"), 0, 0)
    grid.addWidget(window.log_tail_target_combo, 0, 1)
    grid.addWidget(QLabel("初始行数"), 1, 0)
    grid.addWidget(window.log_tail_lines_spin, 1, 1)
    grid.setColumnStretch(1, 1)

    buttons = QHBoxLayout()
    tail_button = QPushButton("开始 tail")
    tail_button.setObjectName("PrimaryButton")
    tail_button.clicked.connect(window.tail_remote_log)
    stop_button = QPushButton("停止 tail")
    stop_button.clicked.connect(window.stop_current_command)
    for button in (tail_button, stop_button):
        window.command_buttons.append(button)
        buttons.addWidget(button)
    buttons.addStretch(1)
    grid.addLayout(buttons, 2, 0, 1, 2)

    layout.addWidget(build_panel("实时日志", grid))
    layout.addWidget(build_note("普通文件使用 tail -F；journal: 表示 journalctl -f；journal:服务名 表示查看指定 systemd 服务；dmesg 表示 dmesg -w。"))
    layout.addStretch(1)
    return page
