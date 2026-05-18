from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from ui.pages.common import build_note, build_panel


def build_process_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.process_summary_label = None
    window.process_table = None

    list_grid = QGridLayout()
    list_grid.setHorizontalSpacing(10)
    list_grid.setVerticalSpacing(10)
    window.process_filter_edit = QLineEdit()
    window.process_filter_edit.setPlaceholderText("例如 python、yolo、rknn")
    list_button = QPushButton("刷新进程")
    list_button.setObjectName("PrimaryButton")
    list_button.clicked.connect(window.list_remote_processes)
    window.command_buttons.append(list_button)
    list_grid.addWidget(QLabel("过滤关键字"), 0, 0)
    list_grid.addWidget(window.process_filter_edit, 0, 1)
    list_grid.addWidget(list_button, 0, 2)
    list_grid.setColumnStretch(1, 1)
    layout.addWidget(build_panel("远程进程列表", list_grid))

    result_layout = QVBoxLayout()
    window.process_summary_label = QLabel("点击“刷新进程”后显示远端进程。")
    window.process_summary_label.setObjectName("MutedText")
    result_layout.addWidget(window.process_summary_label)
    window.process_table = QTableWidget(0, 5)
    window.process_table.setHorizontalHeaderLabels(["PID", "CPU", "MEM", "运行时长", "命令"])
    window.process_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    window.process_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.process_table.setAlternatingRowColors(True)
    window.process_table.verticalHeader().setVisible(False)
    window.process_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
    window.process_table.setMinimumHeight(220)
    result_layout.addWidget(window.process_table)
    layout.addWidget(build_panel("进程结果", result_layout), 1)

    kill_grid = QGridLayout()
    kill_grid.setHorizontalSpacing(10)
    kill_grid.setVerticalSpacing(10)
    window.kill_pid_edit = QLineEdit()
    window.kill_pid_edit.setPlaceholderText("PID")
    window.pkill_pattern_edit = QLineEdit()
    window.pkill_pattern_edit.setPlaceholderText("按命令关键字结束，例如 yolo")
    kill_pid_button = QPushButton("结束 PID")
    kill_pid_button.clicked.connect(window.kill_remote_pid)
    pkill_button = QPushButton("按关键字结束")
    pkill_button.clicked.connect(window.pkill_remote_pattern)
    for button in (kill_pid_button, pkill_button):
        window.command_buttons.append(button)
    kill_grid.addWidget(QLabel("PID"), 0, 0)
    kill_grid.addWidget(window.kill_pid_edit, 0, 1)
    kill_grid.addWidget(kill_pid_button, 0, 2)
    kill_grid.addWidget(QLabel("关键字"), 1, 0)
    kill_grid.addWidget(window.pkill_pattern_edit, 1, 1)
    kill_grid.addWidget(pkill_button, 1, 2)
    kill_grid.setColumnStretch(1, 1)
    layout.addWidget(build_panel("结束远程进程", kill_grid))
    layout.addWidget(build_note("结束进程会发送 TERM 信号。按关键字结束使用 pkill -f，请确认关键字足够精确。"))
    layout.addStretch(1)
    return page
