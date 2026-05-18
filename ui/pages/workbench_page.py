from PyQt5.QtWidgets import (
    QAbstractItemView,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtCore import Qt

from ui.pages.common import build_note, build_panel


def build_workbench_page(window):
    page = QWidget()
    layout = QVBoxLayout(page)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(12)
    window.workbench_labels = {}

    summary_grid = QGridLayout()
    summary_grid.setHorizontalSpacing(12)
    summary_grid.setVerticalSpacing(10)
    _add_field(window, summary_grid, "设备", "device", 0, 0)
    _add_field(window, summary_grid, "SSH", "ssh", 0, 2)
    _add_field(window, summary_grid, "项目", "project", 1, 0)
    _add_field(window, summary_grid, "远端路径", "remote_root", 1, 2)
    _add_field(window, summary_grid, "本地路径", "local_root", 2, 0, col_span=3)
    summary_grid.setColumnStretch(1, 1)
    summary_grid.setColumnStretch(3, 1)
    layout.addWidget(build_panel("当前工作上下文", summary_grid))

    action_layout = QHBoxLayout()
    for text, handler, primary in [
        ("一键同步构建运行", window.workflow_sync_build_run, True),
        ("同步", window.workflow_sync, True),
        ("构建", window.workflow_build, True),
        ("运行", window.workflow_run, True),
        ("日志", window.workflow_logs, False),
        ("停止", window.workflow_stop, False),
        ("诊断报告", window.generate_diagnostic_report, False),
    ]:
        button = QPushButton(text)
        if primary:
            button.setObjectName("PrimaryButton")
        button.clicked.connect(handler)
        window.command_buttons.append(button)
        action_layout.addWidget(button)
    action_layout.addStretch(1)
    layout.addWidget(build_panel("开发工作流", action_layout))

    task_layout = QVBoxLayout()
    window.task_center_table = QTableWidget(0, 5)
    window.task_center_table.setHorizontalHeaderLabels(["通道", "状态", "任务", "耗时", "详情"])
    window.task_center_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    window.task_center_table.setSelectionBehavior(QAbstractItemView.SelectRows)
    window.task_center_table.setAlternatingRowColors(True)
    window.task_center_table.verticalHeader().setVisible(False)
    window.task_center_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
    window.task_center_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
    window.task_center_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
    window.task_center_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
    window.task_center_table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Stretch)
    window.task_center_table.setMinimumHeight(150)
    task_layout.addWidget(window.task_center_table)

    task_buttons = QHBoxLayout()
    for text, handler in [
        ("停止短命令", window.stop_short_command),
        ("停止长命令", window.stop_long_command),
        ("取消 SFTP", window.cancel_sftp_task),
        ("取消模型扫描", window.cancel_model_scan_task),
        ("重连资源监控", window.reconnect_resource_monitor),
    ]:
        button = QPushButton(text)
        button.clicked.connect(handler)
        task_buttons.addWidget(button)
    task_buttons.addStretch(1)
    task_layout.addLayout(task_buttons)
    window.task_center_summary_label = QLabel("任务中心就绪")
    window.task_center_summary_label.setObjectName("MutedText")
    task_layout.addWidget(window.task_center_summary_label)
    layout.addWidget(build_panel("任务中心", task_layout))

    history_layout = QVBoxLayout()
    window.task_history_text = QLabel("暂无任务历史")
    window.task_history_text.setObjectName("MutedText")
    window.task_history_text.setWordWrap(True)
    window.task_history_text.setTextInteractionFlags(Qt.TextSelectableByMouse)
    history_layout.addWidget(window.task_history_text)
    layout.addWidget(build_panel("最近任务", history_layout))

    layout.addWidget(build_note("工作台命令使用顶部选中的设备和项目配置。长时间运行的日志 tail 可用底部“停止当前命令”结束。"))
    layout.addStretch(1)
    return page


def _add_field(window, layout, title, key, row, column, col_span=1):
    title_label = QLabel(title)
    title_label.setObjectName("MutedText")
    value_label = QLabel("-")
    value_label.setObjectName("PanelLead")
    value_label.setWordWrap(True)
    value_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
    window.workbench_labels[key] = value_label
    layout.addWidget(title_label, row, column)
    layout.addWidget(value_label, row, column + 1, 1, col_span)
